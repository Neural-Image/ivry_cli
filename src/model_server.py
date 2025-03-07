import threading
from cog.config import Config
from cog.server.http import create_app
import uvicorn
from cog.mode import Mode
import logging
import asyncio
import httpx
from datetime import datetime, timezone
import structlog
import sys
import signal
import os
from cog.server.http import schema, Server, is_port_in_use,signal_ignore, signal_set_event


from dotenv import load_dotenv
load_dotenv()  

def inspect_logging_configuration():
    print("\n=== Logging Configuration ===")
    root_logger = logging.getLogger()
    print(f"Root Logger Level: {logging.getLevelName(root_logger.level)}")
    print(f"Handlers: {root_logger.handlers}")

    for handler in root_logger.handlers:
        print(f"\nHandler: {handler}")
        print(f"  Level: {logging.getLevelName(handler.level)}")
        print(f"  Formatter: {handler.formatter}")
        print(f"  Filters: {handler.filters}")

log = structlog.get_logger("model_server")        

async def send_health_status_periodically(app, remote_endpoint: str, interval: int = 60):
    async with httpx.AsyncClient() as client:
        while True:
            # # Prepare the health payload.
            payload = {
                "health": app.state.health.name,
                "timestamp": datetime.now(tz=timezone.utc).isoformat()
            }
            # try:
            #     # Send a POST request to the remote endpoint.
            #     response = await client.post(remote_endpoint, json=payload)
            #     response.raise_for_status()
            # except Exception as e:
            #     app.logger.error("Failed to send health status", exc_info=e)
            # Wait for the specified interval before sending again.
            log.info(payload)
            await asyncio.sleep(interval)        

def main(args):
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

    @app.on_event("startup")
    async def start_health_reporting():
        # Schedule the health reporting task and save it in the app's state.
        app.state.health_task = asyncio.create_task(
            send_health_status_periodically(app, "", interval=3600)
        )

    @app.on_event("shutdown")
    async def stop_health_reporting():
        # Cancel the health reporting task if it exists.
        health_task = getattr(app.state, "health_task", None)
        if health_task:
            health_task.cancel()

    host: str = args.host

    port = int(os.getenv("PORT", "3009"))
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
    main()
