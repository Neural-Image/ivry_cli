import argparse
import asyncio
import functools
import logging
import os
import signal
import socket
import sys
import textwrap
import threading
import traceback
from datetime import datetime, timezone
from enum import Enum, auto, unique
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, Optional, Type
import httpx
import structlog
import uvicorn
from fastapi import Body, FastAPI, Header, Path, Response, BackgroundTasks
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import HTTPException
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .. import schema
from ..config import Config
from ..errors import PredictorNotSet
from ..files import upload_file
from ..json import upload_files
from ..logging import setup_logging
from ..mode import Mode
from ..types import PYDANTIC_V2

from pathlib import Path as filePath
import uuid
from datetime import datetime
import traceback
from pydantic import BaseModel
import mimetypes
import json
import requests

try:
    from .._version import __version__
except ImportError:
    __version__ = "dev"

if PYDANTIC_V2:
    from .helpers import (
        unwrap_pydantic_serialization_iterators,
        update_openapi_schema_for_pydantic_2,
    )

from .probes import ProbeHelper
from .runner import (
    PredictionRunner,
    RunnerBusyError,
    SetupResult,
    UnknownPredictionError,
)
from .telemetry import make_trace_context, trace_context
from .worker import make_worker

if TYPE_CHECKING:
    from typing import ParamSpec, TypeVar  # pylint: disable=import-outside-toplevel

    P = ParamSpec("P")  # pylint: disable=invalid-name
    T = TypeVar("T")  # pylint: disable=invalid-name

log = structlog.get_logger("cog.server.http")


@unique
class Health(Enum):
    UNKNOWN = auto()
    STARTING = auto()
    READY = auto()
    BUSY = auto()
    SETUP_FAILED = auto()
    DEFUNCT = auto()


class MyState:
    health: Health
    setup_result: Optional[SetupResult]


class MyFastAPI(FastAPI):
    # TODO: not, strictly speaking, legal
    # https://github.com/microsoft/pyright/issues/5933
    # but it'd need a FastAPI patch to fix
    state: MyState  # type: ignore


def add_setup_failed_routes(
    app: MyFastAPI,  # pylint: disable=redefined-outer-name
    started_at: datetime,
    msg: str,
) -> None:
    print(msg)
    result = SetupResult(
        started_at=started_at,
        completed_at=datetime.now(tz=timezone.utc),
        logs=[msg],
        status=schema.Status.FAILED,
    )
    app.state.setup_result = result
    app.state.health = Health.SETUP_FAILED

    @app.get("/health-check")
    async def healthcheck_startup_failed() -> Any:
        assert app.state.setup_result
        return jsonable_encoder(
            {
                "status": app.state.health.name,
                "setup": app.state.setup_result.to_dict(),
            }
        )


def create_app(  # pylint: disable=too-many-arguments,too-many-locals,too-many-statements
    cog_config: Config,
    shutdown_event: Optional[threading.Event],  # pylint: disable=redefined-outer-name
    app_threads: Optional[int] = None,
    upload_url: Optional[str] = None,
    mode: Mode = Mode.PREDICT,
    is_build: bool = False,
    await_explicit_shutdown: bool = False,  # pylint: disable=redefined-outer-name
) -> MyFastAPI:
    app = MyFastAPI(  # pylint: disable=redefined-outer-name
        title="Ivry",  # TODO: mention model name?
        # version=None # TODO
    )
    print("cog_config",cog_config.get_predictor_ref(mode=Mode.PREDICT))
    if cog_config.get_predictor_ref(mode=Mode.PREDICT) != "functions.py":
        def custom_openapi() -> Dict[str, Any]:
            if not app.openapi_schema:
                openapi_schema = get_openapi(
                    title="Ivry",
                    openapi_version="3.0.2",
                    version="0.1.0",
                    routes=app.routes,
                )

                # Pydantic 2 changes how optional fields are represented in OpenAPI schema.
                # See: https://github.com/tiangolo/fastapi/pull/9873#issuecomment-1997105091
                if PYDANTIC_V2:
                    update_openapi_schema_for_pydantic_2(openapi_schema)

                app.openapi_schema = openapi_schema

            return app.openapi_schema

        app.openapi = custom_openapi

        app.state.health = Health.STARTING
        app.state.setup_result = None
        started_at = datetime.now(tz=timezone.utc)

        # shutdown is needed no matter what happens
        @app.post("/shutdown")
        async def start_shutdown() -> Any:
            log.info("shutdown requested via http")
            if shutdown_event:
                shutdown_event.set()
            return JSONResponse({}, status_code=200)

        try:
            InputType, OutputType = cog_config.get_predictor_types(mode=Mode.PREDICT)
        except Exception:  # pylint: disable=broad-exception-caught
            msg = "Error while loading predictor:\n\n" + traceback.format_exc()
            add_setup_failed_routes(app, started_at, msg)
            return app

        worker = make_worker(predictor_ref=cog_config.get_predictor_ref(mode=mode))
        runner = PredictionRunner(worker=worker)

        class PredictionRequest(schema.PredictionRequest.with_types(input_type=InputType)):
            pass
        PredictionResponse = schema.PredictionResponse.with_types(  # pylint: disable=invalid-name
            input_type=InputType, output_type=OutputType
        )

        if app_threads is None:
            app_threads = 1 if cog_config.requires_gpu else _cpu_count()
        http_semaphore = asyncio.Semaphore(app_threads)

        def limited(f: "Callable[P, Awaitable[T]]") -> "Callable[P, Awaitable[T]]":
            @functools.wraps(f)
            async def wrapped(*args: "P.args", **kwargs: "P.kwargs") -> "T":  # pylint: disable=redefined-outer-name
                async with http_semaphore:
                    return await f(*args, **kwargs)

            return wrapped

        index_document = {
            "cog_version": __version__,
            "docs_url": "/docs",
            "openapi_url": "/openapi.json",
            "shutdown_url": "/shutdown",
            "healthcheck_url": "/health-check",
            "predictions_url": "/predictions",
            "predictions_idempotent_url": "/predictions/{prediction_id}",
            "predictions_cancel_url": "/predictions/{prediction_id}/cancel",
        }

        if cog_config.predictor_train_ref:
            try:
                TrainingInputType, TrainingOutputType = cog_config.get_predictor_types(
                    Mode.TRAIN
                )

                class TrainingRequest(
                    schema.TrainingRequest.with_types(input_type=TrainingInputType)
                ):
                    pass

                TrainingResponse = schema.TrainingResponse.with_types(  # pylint: disable=invalid-name
                    input_type=TrainingInputType, output_type=TrainingOutputType
                )

                @app.post(
                    "/trainings",
                    response_model=TrainingResponse,
                    response_model_exclude_unset=True,
                )
                def train(
                    request: TrainingRequest = Body(default=None),
                    prefer: Optional[str] = Header(default=None),
                    traceparent: Optional[str] = Header(
                        default=None, include_in_schema=False
                    ),
                    tracestate: Optional[str] = Header(
                        default=None, include_in_schema=False
                    ),
                ) -> Any:  # type: ignore
                    respond_async = prefer == "respond-async"

                    with trace_context(make_trace_context(traceparent, tracestate)):
                        return _predict(
                            request=request,
                            response_type=TrainingResponse,
                            respond_async=respond_async,
                        )

                @app.put(
                    "/trainings/{training_id}",
                    response_model=TrainingResponse,
                    response_model_exclude_unset=True,
                )
                def train_idempotent(
                    training_id: str = Path(..., title="Training ID"),
                    request: TrainingRequest = Body(..., title="Training Request"),
                    prefer: Optional[str] = Header(default=None),
                    traceparent: Optional[str] = Header(
                        default=None, include_in_schema=False
                    ),
                    tracestate: Optional[str] = Header(
                        default=None, include_in_schema=False
                    ),
                ) -> Any:
                    if request.id is not None and request.id != training_id:
                        body = {
                            "loc": ("body", "id"),
                            "msg": "training ID must match the ID supplied in the URL",
                            "type": "value_error",
                        }
                        raise HTTPException(422, [body])

                    # We've already checked that the IDs match, now ensure that an ID is
                    # set on the prediction object
                    request.id = training_id

                    # If the prediction service is already running a prediction with a
                    # matching ID, return its current state.
                    if runner.is_busy():
                        task = runner.get_predict_task(request.id)
                        if task:
                            return JSONResponse(
                                jsonable_encoder(task.result),
                                status_code=202,
                            )

                    # TODO: spec-compliant parsing of Prefer header.
                    respond_async = prefer == "respond-async"

                    with trace_context(make_trace_context(traceparent, tracestate)):
                        return _predict(
                            request=request,
                            response_type=TrainingResponse,
                            respond_async=respond_async,
                        )

                @app.post("/trainings/{training_id}/cancel")
                def cancel_training(
                    training_id: str = Path(..., title="Training ID"),
                ) -> Any:
                    return cancel(training_id)

                index_document.update(
                    {
                        "trainings_url": "/trainings",
                        "trainings_idempotent_url": "/trainings/{training_id}",
                        "trainings_cancel_url": "/trainings/{training_id}/cancel",
                    }
                )

            except Exception as e:  # pylint: disable=broad-exception-caught
                if isinstance(e, (PredictorNotSet, FileNotFoundError)) and not is_build:
                    pass  # ignore missing train.py for backward compatibility with existing "bad" models in use
                else:
                    app.state.health = Health.SETUP_FAILED
                    msg = "Error while loading trainer:\n\n" + traceback.format_exc()
                    add_setup_failed_routes(app, started_at, msg)
                    return app

        @app.on_event("startup")
        def startup() -> None:
            # check for early setup failures
            if (
                app.state.setup_result
                and app.state.setup_result.status == schema.Status.FAILED
            ):
                # signal shutdown if interactive run
                if shutdown_event and not await_explicit_shutdown:
                    shutdown_event.set()
            else:
                setup_task = runner.setup()
                setup_task.add_done_callback(_handle_setup_done)

        @app.on_event("shutdown")
        def shutdown() -> None:
            worker.terminate()

        @app.get("/")
        async def root() -> Any:
            return index_document

        @app.get("/health-check")
        async def healthcheck() -> Any:
            if app.state.health == Health.READY:
                health = Health.BUSY if runner.is_busy() else Health.READY
            else:
                health = app.state.health
            setup = app.state.setup_result.to_dict() if app.state.setup_result else {}
            return jsonable_encoder({"status": health.name, "setup": setup})

        @limited
        @app.post(
            "/predictions",
            response_model=PredictionResponse,
            response_model_exclude_unset=True,
        )
        async def predict(
            request: PredictionRequest = Body(default=None),
            prefer: Optional[str] = Header(default=None),
            traceparent: Optional[str] = Header(default=None, include_in_schema=False),
            tracestate: Optional[str] = Header(default=None, include_in_schema=False),
        ) -> Any:  # type: ignore
            """
            Run a single prediction on the model
            """
            # TODO: spec-compliant parsing of Prefer header.
            respond_async = prefer == "respond-async"
            with trace_context(make_trace_context(traceparent, tracestate)):
                return _predict(
                    request=request,
                    response_type=PredictionResponse,
                    respond_async=respond_async,
                )

        @limited
        @app.put(
            "/predictions/{prediction_id}",
            response_model=PredictionResponse,
            response_model_exclude_unset=True,
        )
        async def predict_idempotent(
            prediction_id: str = Path(..., title="Prediction ID"),
            request: PredictionRequest = Body(..., title="Prediction Request"),
            prefer: Optional[str] = Header(default=None),
            traceparent: Optional[str] = Header(default=None, include_in_schema=False),
            tracestate: Optional[str] = Header(default=None, include_in_schema=False),
        ) -> Any:
            """
            Run a single prediction on the model (idempotent creation).
            """
            if request.id is not None and request.id != prediction_id:
                body = {
                    "loc": ("body", "id"),
                    "msg": "prediction ID must match the ID supplied in the URL",
                    "type": "value_error",
                }
                raise HTTPException(422, [body])

            # We've already checked that the IDs match, now ensure that an ID is
            # set on the prediction object
            request.id = prediction_id

            # If the prediction service is already running a prediction with a
            # matching ID, return its current state.
            if runner.is_busy():
                task = runner.get_predict_task(request.id)
                if task:
                    return JSONResponse(
                        jsonable_encoder(task.result),
                        status_code=202,
                    )

            # TODO: spec-compliant parsing of Prefer header.
            respond_async = prefer == "respond-async"

            with trace_context(make_trace_context(traceparent, tracestate)):
                return _predict(
                    request=request,
                    response_type=PredictionResponse,
                    respond_async=respond_async,
                )

        def _predict(
            *,
            request: Optional[PredictionRequest],
            response_type: Type[schema.PredictionResponse],
            respond_async: bool = False,
        ) -> Response:
            # [compat] If no body is supplied, assume that this model can be run
            # with empty input. This will throw a ValidationError if that's not
            # possible.
            if request is None:
                request = PredictionRequest(input={})
            # [compat] If body is supplied but input is None, set it to an empty
            # dictionary so that later code can be simpler.
            if request.input is None:
                request.input = {}  # pylint: disable=attribute-defined-outside-init

            task_kwargs = {}
            if respond_async:
                # For now, we only ask PredictionService to handle file uploads for
                # async predictions. This is unfortunate but required to ensure
                # backwards-compatible behaviour for synchronous predictions.
                task_kwargs["upload_url"] = upload_url
            try:
                predict_task = runner.predict(request, task_kwargs=task_kwargs)
            except RunnerBusyError:
                return JSONResponse(
                    {"detail": "Already running a prediction"}, status_code=409
                )

            if hasattr(request.input, "cleanup"):
                predict_task.add_done_callback(lambda _: request.input.cleanup())

            #NOTE this can be used to handle file removal
            # predict_task.add_done_callback(lambda rez: print("done callback", rez))

            predict_task.add_done_callback(_handle_predict_done)

            if respond_async:
                return JSONResponse(
                    jsonable_encoder(predict_task.result),
                    status_code=202,
                )

            # Otherwise, wait for the prediction to complete...
            predict_task.wait()

            # ...and return the result.
            if PYDANTIC_V2:
                response_object = unwrap_pydantic_serialization_iterators(
                    predict_task.result.model_dump()
                )
            else:
                response_object = predict_task.result.dict()
            try:
                _ = response_type(**response_object)
            except ValidationError as e:
                _log_invalid_output(e)
                raise HTTPException(status_code=500, detail=str(e)) from e
            response_object["output"] = upload_files(
                response_object["output"],
                upload_file=lambda fh: upload_file(fh, request.output_file_prefix),  # type: ignore
            )

            # FIXME: clean up output files
            encoded_response = jsonable_encoder(response_object)
            return JSONResponse(content=encoded_response)

        @app.post("/predictions/{prediction_id}/cancel")
        async def cancel(prediction_id: str = Path(..., title="Prediction ID")) -> Any:
            """
            Cancel a running prediction
            """
            if not runner.is_busy():
                return JSONResponse({}, status_code=404)
            try:
                runner.cancel(prediction_id)
            except UnknownPredictionError:
                return JSONResponse({}, status_code=404)
            return JSONResponse({}, status_code=200)

        def _handle_predict_done(response: schema.PredictionResponse) -> None:
            if response._fatal_exception:
                _maybe_shutdown(response._fatal_exception)

        def _handle_setup_done(setup_result: SetupResult) -> None:
            app.state.setup_result = setup_result

            if app.state.setup_result.status == schema.Status.SUCCEEDED:
                app.state.health = Health.READY

                # In kubernetes, mark the pod as ready now setup has completed.
                probes = ProbeHelper()
                probes.ready()
            else:
                _maybe_shutdown(Exception("setup failed"), status=Health.SETUP_FAILED)

        def _maybe_shutdown(exc: BaseException, *, status: Health = Health.DEFUNCT) -> None:
            log.error("encountered fatal error", exc_info=exc)
            app.state.health = status
            if shutdown_event and not await_explicit_shutdown:
                log.error("shutting down immediately")
                shutdown_event.set()
            else:
                log.error("awaiting explicit shutdown")
    else:
        ### For Function
        ### TODO:
        # 1. Add string result validation
        # 2. Mutilple file upload bug fix
        
        webhook_url = os.environ.get("WEBHOOK_URL", "https://www.ivry.co/api/webhook/execution") 
        #cog_config.get_predictor_ref(mode=Mode.PREDICT)
        functions = cog_config.get_function_dicts(mode=Mode.PREDICT)
        print("Functions loaded:", functions)
        class WorkflowInstance(BaseModel):
            function: str
            params: dict
            execution_id: int
        
        
        # Create an async wrapper for possibly synchronous functions
        async def _execute_function_async(func_name: str, params: Dict[str, Any]):
            
            func = functions[func_name]
            if asyncio.iscoroutinefunction(func):
                return await func(**params)
            else:
                return await asyncio.to_thread(func, **params)

        
        
        # Function to send results to webhook
        async def send_to_webhook(instance: WorkflowInstance, results: Any):
            async with httpx.AsyncClient() as client:
                # 处理结果中的文件路径
                files_info = []
                
                # 递归处理结果中的文件路径 - 改进文件检测逻辑
                def process_output(output, path=""):
                    nonlocal files_info
                    
                    if isinstance(output, dict):
                        processed_output = {}
                        for key, value in output.items():
                            current_path = f"{path}.{key}" if path else key
                            processed_output[key] = process_output(value, current_path)
                        return processed_output
                    
                    elif isinstance(output, list):
                        processed_list = []
                        for i, item in enumerate(output):
                            processed_list.append(process_output(item, f"{path}[{i}]"))
                        return processed_list
                    
                    # 改进文件路径检测逻辑
                    elif isinstance(output, str) and (
                        os.path.isfile(output) or 
                        (output.startswith(('/', './')) and '.' in os.path.basename(output))
                    ):
                        file_path = str(output)
                        print(f"Detected file: {file_path}")
                        files_info.append({
                            "path": file_path,
                            "field_path": path
                        })
                        return {"file_reference": os.path.basename(file_path)}
                    
                    elif isinstance(output, filePath):
                        file_path = str(output)
                        print(f"Detected Path object: {file_path}")
                        files_info.append({
                            "path": file_path,
                            "field_path": path
                        })
                        return {"file_reference": os.path.basename(file_path)}
                    
                    else:
                        return output
                
                # 处理结果
                processed_results = process_output(results)
                print(f"Processed results: {processed_results}")
                print(f"Detected files: {files_info}")
                
                # 构建初始payload
                payload = {
                    "execution_id": instance.execution_id,
                    "results": processed_results,
                    "files": []
                }
                
                # 上传所有文件 - 添加更详细的日志
                webhook_url = os.environ.get("WEBHOOK_URL", "https://www.ivry.co/api/webhook/execution")
                print(f"Using webhook URL: {webhook_url}")
                
                # 直接在此处实现文件上传，避免跨函数调用的问题
                for file_info in files_info:
                    file_path = file_info["path"]
                    if not os.path.exists(file_path):
                        print(f"File not found: {file_path}")
                        continue
                        
                    print(f"Uploading file: {file_path}")
                    file_name = os.path.basename(file_path)
                    mime_type, _ = mimetypes.guess_type(file_name)
                    
                    #try:
                    with open(file_path, 'rb') as f:
                        #files = {'file': (file_name, f.read(), mime_type)}
                        #data = {'workflow_run_id': instance.execution_id}
                        with open(file_path, 'rb') as file:
                            file_content = file.read()
                        
                        upload_url = f"https://www.ivry.co/api/cli/upload/{file_name}"
                        print(f"Sending file to: {upload_url}")
                        
                        headers = {
                            'Content-Type': 'content_type',
                        }

                        # 使用同步请求确保上传完成
                        upload_response = requests.put(upload_url, data=file_content, headers=headers)
                        upload_response.raise_for_status()
                        location_url = upload_response.headers.get('location')
                        upload_result = upload_response.json()
                        print(f"Upload response: {upload_result}")
                        print(f"Upload response location url: {location_url}")
                        file_url = upload_result.get("file_url", "")
                        if not file_url:
                            print("Warning: No file_url in upload response")
                        
                        file_data = {
                            "field_path": file_info["field_path"],
                            "file_name": file_name,
                            "file_url": file_url
                        }
                        payload["files"].append(file_data)
                        payload["results"] = [location_url]
                        print(f"Added file to payload: {file_data}")
                        os.remove(file_path)  # 删除本地文件
                    #except Exception as e:
                    #    print(f"Error uploading file {file_path}: {str(e)}")
                
                # 发送结果
                webhook_endpoint = webhook_url
                print(f"Sending webhook to: {webhook_endpoint}")
                print(f"Payload: {json.dumps(payload, indent=2)}")
                
                try:
                    response = await client.post(webhook_endpoint, json=payload)
                    print(f"Webhook response status: {response.status_code}")
                    print(f"Webhook response body: {response.text}")
                    response.raise_for_status()
                    print(f"Webhook notification sent successfully")
                    
                except Exception as e:
                    print(f"Failed to send webhook: {str(e)}")

        # Background task handler
        async def process_workflow_task(instance: WorkflowInstance):
            results = await _execute_function_async(instance.function, instance.params)
            await send_to_webhook(instance, results)

        @app.post("/execute")
        async def execute(instance: WorkflowInstance, background_tasks: BackgroundTasks):
            if instance.function not in functions:
                raise HTTPException(status_code=400, detail="Function not found")
            background_tasks.add_task(process_workflow_task, instance)
            return {
                "status": "success",
                "message": f"Workflow {instance.execution_id} execution started",
                "execution_id": instance.execution_id,
            }

        
        @app.get("/health-check")
        async def health_check():
            return {"status": "READY"}
        
        
        ###

    return app


def _log_invalid_output(error: Any) -> None:
    log.error(
        textwrap.dedent(
            f"""\
            The return value of predict() was not valid:

            {error}

            Check that your predict function is in this form, where `output_type` is the same as the type you are returning (e.g. `str`):

                def predict(...) -> output_type:
                    ...
           """
        )
    )






class Server(uvicorn.Server):
    def start(self) -> None:
        self._thread = threading.Thread(target=self.run)  # pylint: disable=attribute-defined-outside-init
        self._thread.start()

    def stop(self) -> None:
        log.info("stopping server")
        self.should_exit = True  # pylint: disable=attribute-defined-outside-init

        self._thread.join(timeout=5)
        if not self._thread.is_alive():
            return

        log.warn("failed to exit after 5 seconds, setting force_exit")
        self.force_exit = True  # pylint: disable=attribute-defined-outside-init
        self._thread.join(timeout=5)
        if not self._thread.is_alive():
            return

        log.warn("failed to exit after another 5 seconds, sending SIGKILL")
        os.kill(os.getpid(), signal.SIGKILL)


def is_port_in_use(port: int) -> bool:  # pylint: disable=redefined-outer-name
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("localhost", port)) == 0


def signal_ignore(signum: Any, frame: Any) -> None:  # pylint: disable=unused-argument
    log.warn("Got a signal to exit, ignoring it...", signal=signal.Signals(signum).name)


def signal_set_event(event: threading.Event) -> Callable[[Any, Any], None]:
    def _signal_set_event(signum: Any, frame: Any) -> None:  # pylint: disable=unused-argument
        event.set()

    return _signal_set_event


def _cpu_count() -> int:
    try:
        return len(os.sched_getaffinity(0)) or 1  # type: ignore
    except AttributeError:  # not available on every platform
        return os.cpu_count() or 1


def parse_args(args_list=None):
    parser = argparse.ArgumentParser(description="Cog HTTP server")
    parser.add_argument(
        "-v", "--version", action="store_true", help="Show version and exit"
    )
    parser.add_argument(
        "--host",
        dest="host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to",
    )
    parser.add_argument(
        "--threads",
        dest="threads",
        type=int,
        default=4,
        help="Number of worker processes. Defaults to number of CPUs, or 1 if using a GPU.",
    )
    parser.add_argument(
        "--upload_url",
        dest="upload_url",
        type=str,
        default=None,
        help="An endpoint for Cog to PUT output files to",
    )
    parser.add_argument(
        "--await-explicit-shutdown",
        dest="await_explicit_shutdown",
        type=bool,
        default=False,
        help="Ignore SIGTERM and wait for a request to /shutdown (or a SIGINT) before exiting",
    )
    parser.add_argument(
        "--x-mode",
        dest="mode",
        type=Mode,
        default=Mode.PREDICT,
        choices=list(Mode),
        help="Experimental: Run in 'predict' or 'train' mode",
    )
    
    if args_list is not None:
        args = parser.parse_args(args_list)
    else:
        args = parser.parse_args()

    return args    

def main(args):
    if args.version:
        print(f"cog.server.http {__version__}")
        sys.exit(0)

    # log level is configurable so we can make it quiet or verbose for `cog predict`
    # cog predict --debug       # -> debug
    # cog predict               # -> warning
    # docker run <image-name>   # -> info (default)
    log_level = logging.getLevelName(os.environ.get("COG_LOG_LEVEL", "INFO").upper())
    # setup_logging(log_level=log_level) # commented out to avoid module logger propagate

    shutdown_event = threading.Event()

    await_explicit_shutdown = args.await_explicit_shutdown
    if await_explicit_shutdown:
        signal.signal(signal.SIGTERM, signal_ignore)
    else:
        signal.signal(signal.SIGTERM, signal_set_event(shutdown_event))

    app = create_app(
        cog_config=Config(),
        shutdown_event=shutdown_event,
        app_threads=args.threads,
        upload_url=args.upload_url,
        mode=args.mode,
        await_explicit_shutdown=await_explicit_shutdown,
    )

    host: str = args.host

    port = int(os.getenv("PORT", "3009"))
    print("starting server with port:", port)
    if is_port_in_use(port):
        log.error(f"Port {port} is already in use")
        sys.exit(1)

    cfg = uvicorn.config.LOGGING_CONFIG
    cfg["loggers"]["uvicorn"]["handlers"] = []
    server_config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_config=None,
        # This is the default, but to be explicit: only run a single worker
        workers=1,
    )

    s = Server(config=server_config)
    s.start()

    try:
        shutdown_event.wait()
    except KeyboardInterrupt:
        pass

    s.stop()

    # return error exit code when setup failed and cog is running in interactive mode (not k8s)
    if (
        app.state.setup_result
        and app.state.setup_result.status == schema.Status.FAILED
        and not await_explicit_shutdown
    ):
        sys.exit(-1)


if __name__ == "__main__":
    main(parse_args())
