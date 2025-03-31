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

import structlog
import uvicorn
from fastapi import Body, FastAPI, Header, Path, Response
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

from pathlib import Path
import uuid
from datetime import datetime
import traceback


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

    ### Add Verbal Labs API functions
    def create_verbal_labs_routes(app):

        from fastapi import Query, Request
        from fastapi.responses import StreamingResponse
        from pydantic import BaseModel
        from typing import List, Dict, Any, Optional, AsyncGenerator
        import json
        import os
        import importlib.util
        import sys
        import aiohttp
        import asyncio

        
        class ClientAttachment(BaseModel):
            name: str
            contentType: str
            url: str

        class ToolInvocationState(str, Enum):
            CALL = 'call'
            PARTIAL_CALL = 'partial-call'
            RESULT = 'result'

        class ToolInvocation(BaseModel):
            state: ToolInvocationState
            toolCallId: str
            toolName: str
            args: Any
            result: Optional[Any] = None

        class ClientMessage(BaseModel):
            role: str
            content: str
            experimental_attachments: Optional[List[ClientAttachment]] = None
            toolInvocations: Optional[List[ToolInvocation]] = None
        
        class ChatRequest(BaseModel):
            messages: List[ClientMessage]

        def convert_to_openai_messages(messages: List[ClientMessage]) -> List[Dict[str, Any]]:
           
            openai_messages = []

            for message in messages:
                parts = []
                tool_calls = []

                parts.append({
                    'type': 'text',
                    'text': message.content
                })

                if message.experimental_attachments:
                    for attachment in message.experimental_attachments:
                        if attachment.contentType.startswith('image'):
                            parts.append({
                                'type': 'image_url',
                                'image_url': {
                                    'url': attachment.url
                                }
                            })
                        elif attachment.contentType.startswith('text'):
                            parts.append({
                                'type': 'text',
                                'text': attachment.url
                            })

                if message.toolInvocations:
                    for toolInvocation in message.toolInvocations:
                        tool_calls.append({
                            "id": toolInvocation.toolCallId,
                            "type": "function",
                            "function": {
                                "name": toolInvocation.toolName,
                                "arguments": json.dumps(toolInvocation.args)
                            }
                        })

                tool_calls_dict = {"tool_calls": tool_calls} if tool_calls else {}

                openai_messages.append({
                    "role": message.role,
                    "content": parts if len(parts) > 1 else parts[0]["text"],
                    **tool_calls_dict,
                })

                if message.toolInvocations:
                    for toolInvocation in message.toolInvocations:
                        if toolInvocation.result is not None:
                            tool_message = {
                                "role": "tool",
                                "tool_call_id": toolInvocation.toolCallId,
                                "content": json.dumps(toolInvocation.result),
                            }
                            openai_messages.append(tool_message)

            return openai_messages

        def load_user_tools(tools_dir: str) -> Dict[str, Any]:

            tools = {}
            
            import requests  # 确保导入requests库
    
            def get_current_weather(latitude, longitude):
                print(f"Fetching weather data for latitude: {latitude}, longitude: {longitude}")
                
                # 参数验证
                try:
                    latitude = float(latitude)
                    longitude = float(longitude)
                except (ValueError, TypeError):
                    return {"error": f"Invalid coordinates: latitude={latitude}, longitude={longitude}. Must be numbers."}
                
                # 范围验证
                if not (-90 <= latitude <= 90):
                    return {"error": f"Invalid latitude: {latitude}. Must be between -90 and 90."}
                
                if not (-180 <= longitude <= 180):
                    return {"error": f"Invalid longitude: {longitude}. Must be between -180 and 180."}
                
                url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m&hourly=temperature_2m&daily=sunrise,sunset&timezone=auto"
                try:
                    response = requests.get(url)
                    response.raise_for_status()
                    data = response.json()
                    
                    # 添加简单描述以提升用户体验
                    if "current" in data:
                        temp = data.get("current", {}).get("temperature_2m")
                        if temp is not None:
                            if temp < 0:
                                data["description"] = f"Very cold at {temp}°C"
                            elif temp < 10:
                                data["description"] = f"Cold at {temp}°C"
                            elif temp < 20:
                                data["description"] = f"Mild at {temp}°C"
                            elif temp < 30:
                                data["description"] = f"Warm at {temp}°C"
                            else:
                                data["description"] = f"Hot at {temp}°C"
                    
                    return data
                except requests.RequestException as e:
                    print(f"Error fetching weather data: {e}")
                    return {"error": str(e)}
            tools["get_current_weather"] = get_current_weather
            return tools

        def prepare_tools_for_api(available_tools: Dict[str, Any]) -> List[Dict[str, Any]]:
 
            tools = []
            
            # 首先查找工具定义目录
            tools_def_dir = "./tools"
            
            if os.path.exists(tools_def_dir):
                # 从JSON文件加载工具定义
                for filename in os.listdir(tools_def_dir):
                    if filename.endswith('.json'):
                        try:
                            with open(os.path.join(tools_def_dir, filename), 'r') as f:
                                tool_def = json.load(f)
                                if isinstance(tool_def, dict) and "function" in tool_def and "name" in tool_def["function"]:
                                    if tool_def["function"]["name"] in available_tools:
                                        tools.append(tool_def)
                        except Exception as e:
                            log.error(f"Error loading tool definition from {filename}: {e}")
            
            # 如果没有找到工具定义，使用天气工具作为默认
            if not tools:
                tools.append({
                    "type": "function",
                    "function": {
                        "name": "get_current_weather",
                        "description": "Get the current weather at a location",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "latitude": {
                                    "type": "number",
                                    "description": "The latitude of the location"
                                },
                                "longitude": {
                                    "type": "number",
                                    "description": "The longitude of the location"
                                },
                            },
                            "required": ["latitude", "longitude"],
                        },
                    },
                })
            
            return tools

        # 在 create_verbal_labs_routes 函数内部添加一个日志功能
        async def stream_chat_completion(client_messages: List[Dict[str, Any]], 
                            tools: List[Dict[str, Any]], 
                            protocol: str) -> AsyncGenerator[str, None]:
            """
            流式返回聊天完成结果
            """
            # 创建日志目录
            logs_dir = Path("./logs/api_requests")
            logs_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建一个唯一的日志文件名
            log_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_id = f"{log_timestamp}_{uuid.uuid4().hex[:8]}"
            log_file = logs_dir / f"openai_request_{log_id}.json"
            log_response_file = logs_dir / f"openai_response_{log_id}.txt"
            debug_log_file = logs_dir / f"openai_debug_{log_id}.txt"
            
            # 创建调试日志文件
            debug_log = open(debug_log_file, 'w', encoding='utf-8')
            debug_log.write(f"=== DEBUG LOG (ID: {log_id}) ===\n\n")
            debug_log.write(f"[DEBUG] Starting stream_chat_completion at {datetime.now().isoformat()}\n")
            debug_log.write(f"[DEBUG] Protocol: {protocol}\n")
            debug_log.write(f"[DEBUG] Messages count: {len(client_messages)}\n")
            debug_log.write(f"[DEBUG] Tools count: {len(tools)}\n")
            debug_log.flush()
            
            # 记录请求
            openai_api_key = os.environ.get("OPENAI_API_KEY", "sk-proj-U5bRRw2dz9uYLKi2Vh4ET3BlbkFJEaMqgvT8HCeb2UDfzF0b")
            if not openai_api_key:
                debug_log.write("[DEBUG] Error: OpenAI API key not set\n")
                debug_log.close()
                yield json.dumps({"error": "OpenAI API key not set"})
                return

            model = os.environ.get("OPENAI_MODEL", "gpt-4o")
            api_base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
            
            debug_log.write(f"[DEBUG] Using model: {model}\n")
            debug_log.write(f"[DEBUG] Using API base: {api_base}\n")
            
            # 准备API请求
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {openai_api_key}",
            }
            
            payload = {
                "model": model,
                "messages": client_messages,
                "stream": True,
            }
            
            if tools:
                payload["tools"] = tools
            
            # 记录请求到日志文件
            try:
                with open(log_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "timestamp": log_timestamp,
                        "request": {
                            "url": f"{api_base}/chat/completions",
                            "headers": headers,
                            "payload": payload
                        }
                    }, f, indent=2, ensure_ascii=False)
                debug_log.write(f"[DEBUG] Request logged to {log_file}\n")
            except Exception as e:
                debug_log.write(f"[DEBUG] Failed to write request log: {e}\n")
                debug_log.flush()
            
            # 存储工具调用状态
            current_tool_calls = []
            
            # 打开响应日志文件
            try:
                response_log = open(log_response_file, 'w', encoding='utf-8')
                response_log.write(f"=== OPENAI API RESPONSE LOG (ID: {log_id}) ===\n\n")
                debug_log.write(f"[DEBUG] Response log file opened: {log_response_file}\n")
            except Exception as e:
                debug_log.write(f"[DEBUG] Failed to open response log file: {e}\n")
                debug_log.flush()
                response_log = None
            
            try:
                debug_log.write(f"[DEBUG] Creating aiohttp session at {datetime.now().isoformat()}\n")
                debug_log.flush()
                
                async with aiohttp.ClientSession() as session:
                    debug_log.write(f"[DEBUG] Sending POST request to {api_base}/chat/completions\n")
                    debug_log.flush()
                    
                    async with session.post(
                        f"{api_base}/chat/completions", 
                        headers=headers, 
                        json=payload
                    ) as response:
                        debug_log.write(f"[DEBUG] Received response with status: {response.status}\n")
                        debug_log.flush()
                        
                        if response.status != 200:
                            error_text = await response.text()
                            error_message = f"OpenAI API error: {response.status} - {error_text}"
                            debug_log.write(f"[DEBUG] Error: {error_message}\n")
                            debug_log.flush()
                            if response_log:
                                response_log.write(f"ERROR: {error_message}\n")
                            yield json.dumps({"error": error_message})
                            return
                        
                        # 解析Stream响应
                        complete_response = ""  # 用于收集完整响应
                        line_count = 0
                        tool_call_complete = False
                        has_final_response = False
                        
                        debug_log.write("[DEBUG] Starting to process response stream\n")
                        debug_log.flush()
                        
                        async for line in response.content:
                            line_count += 1
                            line = line.strip()
                            if not line:
                                continue
                            
                            line_str = line.decode('utf-8')
                            debug_log.write(f"[DEBUG] Line {line_count}: {line_str}\n")
                            debug_log.flush()
                            
                            # 记录原始响应行到日志
                            if response_log:
                                response_log.write(f"{line_str}\n")
                                response_log.flush()
                                
                            if line.startswith(b"data: "):
                                data = line[6:].decode('utf-8')
                                if data == "[DONE]":
                                    debug_log.write(f"[DEBUG] Received [DONE] marker at line {line_count}\n")
                                    debug_log.flush()
                                    
                        
                                    result = "data: [DONE]\n\n"
                                        
                                    if response_log:
                                        response_log.write(f"\n=== YIELDING: {result} ===\n")
                                        response_log.flush()
                                        
                                    yield result
                                    
                                    debug_log.write("[DEBUG] Stream ended with [DONE]\n")
                                    debug_log.write(f"[DEBUG] Tool call complete: {tool_call_complete}\n")
                                    debug_log.write(f"[DEBUG] Has final response: {has_final_response}\n")
                                    debug_log.flush()
                                    
                                    # 检查是否需要获取最终回复
                                    if tool_call_complete and not has_final_response:
                                        debug_log.write("[DEBUG] Tool call is complete but no final response yet. Should request final response.\n")
                                        debug_log.flush()
                                    
                                    continue
                                    
                                try:
                                    chunk = json.loads(data)
                                    debug_log.write(f"[DEBUG] Parsed JSON chunk: {json.dumps(chunk)[:100]}...\n")
                                    debug_log.flush()
                                    
                                    choice = chunk.get("choices", [{}])[0]
                                    delta = choice.get("delta", {})
                                    content = delta.get("content")
                                    
                                    # 检查是否有最终回复
                                    if content is not None:
                                        result = f"data: {json.dumps({'content': content})}\n\n"
                                        yield result
                                        # has_final_response = True
                                        # debug_log.write(f"[DEBUG] Received content: {content}\n")
                                        # debug_log.flush()
                                        
                                        # complete_response += content
                                        # if protocol == 'vercel':
                                        #     result = f'0:{json.dumps(content)}\n'
                                        # else:
                                        #     # 使用标准SSE格式
                                        #     result = f"data: {json.dumps({'choices': [{'delta': {'content': content}}]})}\n\n"
                                        
                                        # if response_log:
                                        #     response_log.write(f"\n=== YIELDING: {result} ===\n")
                                        #     response_log.flush()
                                        # yield result
                                    
                                    # 处理工具调用
                                    tool_calls = delta.get("tool_calls", [])
                                    if tool_calls:
                                        debug_log.write(f"[DEBUG] Received tool calls: {json.dumps(tool_calls)}\n")
                                        debug_log.flush()
                                        
                                        if response_log:
                                            response_log.write(f"\n=== TOOL CALLS: {json.dumps(tool_calls)} ===\n")
                                            response_log.flush()
                                        
                                        for tool_call in tool_calls:
                                            id_val = tool_call.get("id")
                                            index = tool_call.get("index", 0)
                                            function = tool_call.get("function", {})
                                            name = function.get("name")
                                            arguments = function.get("arguments", "")
                                            
                                            # 更新当前工具调用状态
                                            while len(current_tool_calls) <= index:
                                                current_tool_calls.append({
                                                    "id": "",
                                                    "name": "",
                                                    "arguments": ""
                                                })
                                            
                                            if id_val:
                                                current_tool_calls[index]["id"] = id_val
                                            if name:
                                                current_tool_calls[index]["name"] = name
                                            if arguments:
                                                current_tool_calls[index]["arguments"] += arguments
                                            
                                            debug_log.write(f"[DEBUG] Updated tool call at index {index}: {json.dumps(current_tool_calls[index])}\n")
                                            debug_log.flush()
                                    
                                    # 处理完成的工具调用
                                    finish_reason = choice.get("finish_reason")
                                    if finish_reason == "tool_calls":
                                        tool_call_complete = True
                                        debug_log.write(f"[DEBUG] Tool call complete. finish_reason: {finish_reason}\n")
                                        debug_log.write(f"[DEBUG] Complete tool calls: {json.dumps(current_tool_calls)}\n")
                                        debug_log.flush()
                                        
                                        if response_log:
                                            response_log.write(f"\n=== FINISH REASON: tool_calls, TOOL CALLS: {json.dumps(current_tool_calls)} ===\n")
                                            response_log.flush()
                                        
                                        # 发送工具调用
                                        for tool_call in current_tool_calls:
                                            if not tool_call["id"]:
                                                debug_log.write(f"[DEBUG] Skipping tool call with empty ID\n")
                                                continue
                                            
                                            try:
                                                # 确保参数是有效的JSON
                                                args_str = tool_call["arguments"]
                                                args_json = {}
                                                if args_str:
                                                    try:
                                                        args_json = json.loads(args_str)
                                                    except json.JSONDecodeError:
                                                        debug_log.write(f"[DEBUG] Invalid JSON in arguments: {args_str}\n")
                                                        args_json = {"_raw": args_str}
                                                
                                                # 发送工具调用
                                                if protocol == 'vercel':
                                                    result = f'9:{{"toolCallId":"{tool_call["id"]}","toolName":"{tool_call["name"]}","args":{json.dumps(args_json)}}}\n'
                                                else:
                                                    result = f'data: {{"type":"tool_call","id":"{tool_call["id"]}","name":"{tool_call["name"]}","args":{json.dumps(args_json)}}}\n\n'
                                                
                                                debug_log.write(f"[DEBUG] Yielding tool call: {result}\n")
                                                debug_log.flush()
                                                
                                                if response_log:
                                                    response_log.write(f"\n=== YIELDING TOOL CALL: {result} ===\n")
                                                    response_log.flush()
                                                yield result
                                            except Exception as e:
                                                debug_log.write(f"[DEBUG] Error formatting tool call: {str(e)}\n")
                                                debug_log.flush()
                                        
                                        # 获取用户工具并执行
                                        tools_dir = os.environ.get("VERBAL_LABS_TOOLS_DIR", "./tools")
                                        debug_log.write(f"[DEBUG] Loading tools from: {tools_dir}\n")
                                        debug_log.flush()
                                        
                                        available_tools = load_user_tools(tools_dir)
                                        debug_log.write(f"[DEBUG] Available tools: {list(available_tools.keys())}\n")
                                        debug_log.flush()
                                        
                                        # 执行工具并发送结果
                                        for tool_call in current_tool_calls:
                                            if not tool_call["id"]:
                                                continue
                                                
                                            try:
                                                tool_name = tool_call["name"]
                                                debug_log.write(f"[DEBUG] Processing tool call: {tool_name}\n")
                                                debug_log.flush()
                                                
                                                # 解析工具参数
                                                tool_args_str = tool_call["arguments"]
                                                debug_log.write(f"[DEBUG] Tool arguments string: {tool_args_str}\n")
                                                debug_log.flush()
                                                
                                                try:
                                                    tool_args = json.loads(tool_args_str) if tool_args_str else {}
                                                    debug_log.write(f"[DEBUG] Parsed tool arguments: {json.dumps(tool_args)}\n")
                                                except json.JSONDecodeError as e:
                                                    debug_log.write(f"[DEBUG] Failed to parse tool arguments: {e}\n")
                                                    tool_args = {}
                                                
                                                if tool_name in available_tools:
                                                    debug_log.write(f"[DEBUG] Executing tool: {tool_name}\n")
                                                    debug_log.flush()
                                                    
                                                    tool_result = available_tools[tool_name](**tool_args)
                                                    debug_log.write(f"[DEBUG] Tool result: {json.dumps(tool_result)}\n")
                                                    debug_log.flush()
                                                    
                                                    if protocol == 'vercel':
                                                        result = f'a:{{"toolCallId":"{tool_call["id"]}","toolName":"{tool_name}","args":{json.dumps(tool_args)},"result":{json.dumps(tool_result)}}}\n'
                                                    else:
                                                        result = f'data: {{"type":"tool_result","id":"{tool_call["id"]}","result":{json.dumps(tool_result)}}}\n\n'
                                                else:
                                                    debug_log.write(f"[DEBUG] Tool not found: {tool_name}\n")
                                                    debug_log.flush()
                                                    
                                                    error_message = {"error": f"Tool '{tool_name}' not found"}
                                                    if protocol == 'vercel':
                                                        result = f'a:{{"toolCallId":"{tool_call["id"]}","toolName":"{tool_name}","args":{json.dumps(tool_args)},"result":{json.dumps(error_message)}}}\n'
                                                    else:
                                                        result = f'data: {{"type":"tool_result","id":"{tool_call["id"]}","result":{json.dumps(error_message)}}}\n\n'
                                                
                                                debug_log.write(f"[DEBUG] Yielding tool result: {result}\n")
                                                debug_log.flush()
                                                
                                                if response_log:
                                                    response_log.write(f"\n=== YIELDING TOOL RESULT: {result} ===\n")
                                                    response_log.flush()
                                                yield result
                                                
                                            except Exception as e:
                                                debug_log.write(f"[DEBUG] Error executing tool: {e}\n{traceback.format_exc()}\n")
                                                debug_log.flush()
                                                
                                                error_message = {"error": str(e)}
                                                if protocol == 'vercel':
                                                    result = f'a:{{"toolCallId":"{tool_call["id"]}","toolName":"{tool_call["name"]}","args":{json.dumps(tool_args if "tool_args" in locals() else {})},"result":{json.dumps(error_message)}}}\n'
                                                else:
                                                    result = f'data: {{"type":"tool_result","id":"{tool_call["id"]}","result":{json.dumps(error_message)}}}\n\n'
                                                
                                                if response_log:
                                                    response_log.write(f"\n=== YIELDING ERROR: {result} ===\n")
                                                    response_log.flush()
                                                yield result
                                
                                except json.JSONDecodeError as e:
                                    error_message = f"Failed to parse JSON: {data}"
                                    debug_log.write(f"[DEBUG] {error_message}\n")
                                    debug_log.flush()
                                    if response_log:
                                        response_log.write(f"ERROR: {error_message}\n")
                                        response_log.flush()
                                    continue
                        
                        # 请求结束后，检查是否有工具调用但没有最终回复
                        debug_log.write(f"[DEBUG] Stream processing complete. line_count={line_count}, tool_call_complete={tool_call_complete}, has_final_response={has_final_response}\n")
                        
                        if tool_call_complete and not has_final_response:
                            debug_log.write("[DEBUG] Tool call completed but no final response. A second request is needed.\n")
                            debug_log.write("[DEBUG] This appears to be an OpenAI API behavior - tool calls and final response are handled in separate requests.\n")
                            
                            # 这里可以添加代码来发起第二个请求以获取最终回复
                            # 例如：
                            debug_log.write("[DEBUG] Preparing to make second request for final answer...\n")
                            debug_log.flush()
                            
                            # 准备第二个请求
                            second_messages = client_messages.copy()
                            
                            # 添加工具结果消息
                            for tool_call in current_tool_calls:
                                if tool_call["id"] and tool_call["name"] in available_tools:
                                    try:
                                        tool_args = json.loads(tool_call["arguments"]) if tool_call["arguments"] else {}
                                        tool_result = available_tools[tool_call["name"]](**tool_args)
                                        
                                        # 添加工具结果消息
                                        second_messages.append({
                                            "role": "tool",
                                            "tool_call_id": tool_call["id"],
                                            "content": json.dumps(tool_result)
                                        })
                                        
                                        debug_log.write(f"[DEBUG] Added tool result to second request: {json.dumps(tool_result)}\n")
                                    except Exception as e:
                                        debug_log.write(f"[DEBUG] Failed to add tool result: {str(e)}\n")
                            
                            debug_log.write("[DEBUG] Second request would be needed for final answer, but not implemented in this version.\n")
                            debug_log.write("[DEBUG] You can implement second request logic here if needed.\n")
                        
                        # 记录完整响应到日志
                        if response_log:
                            response_log.write(f"\n\n=== COMPLETE RESPONSE ===\n{complete_response}\n")
                            response_log.flush()
                        
                        debug_log.write(f"[DEBUG] Stream processing finished at {datetime.now().isoformat()}\n")
                        debug_log.flush()
                        
            except Exception as e:
                error_message = f"Error in stream_chat_completion: {str(e)}\n{traceback.format_exc()}"
                debug_log.write(f"[DEBUG] CRITICAL ERROR: {error_message}\n")
                debug_log.flush()
                if response_log:
                    response_log.write(f"CRITICAL ERROR: {error_message}\n")
                    response_log.flush()
                
                if protocol == 'vercel':
                    yield f'e:{json.dumps({"error": str(e)})}\n'
                else:
                    yield f'data: {json.dumps({"error": str(e)})}\n\n'
                    
            finally:
                # 确保关闭日志文件
                if response_log:
                    response_log.close()
                debug_log.write(f"[DEBUG] Function stream_chat_completion ended at {datetime.now().isoformat()}\n")
                debug_log.close()

        @app.post("/api/chat")
        async def handle_chat(request: ChatRequest, protocol: str = Query('vercel')):
            """处理聊天请求"""
            print("protocol", protocol)
            # 1. 获取用户定义的工具目录
            tools_dir = os.environ.get("VERBAL_LABS_TOOLS_DIR", "./tools")
            
            # 2. 动态加载用户定义的工具
            available_tools = load_user_tools(tools_dir)
            
            # 3. 准备工具定义
            tools = prepare_tools_for_api(available_tools)
            
            # 4. 准备OpenAI消息格式
            try:
                openai_messages = convert_to_openai_messages(request.messages)
                
                # 5. 设置响应头 - 修改为与repo.har一致的响应头
                response = StreamingResponse(
                    stream_chat_completion(openai_messages, tools, protocol),
                    # 移除 text/event-stream 内容类型，让它使用默认的 application/octet-stream
                    media_type="application/octet-stream"  
                )
                
                # 仍然保留x-vercel-ai-data-stream头
                
                response.headers['x-vercel-ai-data-stream'] = 'v1'
                
                return response
                
            except Exception as e:
                log.error(f"Error in handle_chat: {e}", exc_info=True)
                return {"error": str(e)}
            

    
    




    #create_verbal_labs_routes(app)
    ###

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
