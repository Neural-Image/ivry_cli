from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import uvicorn
from typing import List, Dict, Any
import httpx
import asyncio
from functions import functions

app = FastAPI()


# Create an async wrapper for possibly synchronous functions
async def execute_function_async(func_name: str, params: Dict[str, Any]):
    # Get the function from the functions dictionary
    func = functions[func_name]

    # Check if function is already async
    if asyncio.iscoroutinefunction(func):
        # If it's async, await it directly
        return await func(**params)
    else:
        # If it's synchronous, run it in a thread pool
        return await asyncio.to_thread(func, **params)


# Function to send results to webhook
async def send_to_webhook(execution_id: int, results: Any):
    async with httpx.AsyncClient() as client:
        payload = {
            "execution_id": execution_id,
            "results": results,
        }

        try:
            response = await client.post("http://localhost:3000/api/webhook/execution", json=payload)
            response.raise_for_status()
            print(f"Webhook notification sent: {response.status_code}")
        except Exception as e:
            print(f"Failed to send webhook: {str(e)}")


# Background task handler
async def process_workflow_task(func, params, execution_id):
    # Execute the function asynchronously
    results = await execute_function_async(func, params)
    # Send the results to the webhook
    await send_to_webhook(execution_id, results)


# Define the request data model
class ExecuteRequest(BaseModel):
    function: str
    params: dict
    execution_id: int


@app.post("/execute", status_code=202)
async def execute(request: ExecuteRequest, background_tasks: BackgroundTasks):
    
    # Process the request and handle any potential errors
    try:
        # Execute your function logic here
        # For example: result = await execute_function(request.function, request.params)
        
        # Return success response


        background_tasks.add_task(process_workflow_task, request.function, request.params, request.execution_id)
        # res = await functions[request.function](**request.params)
        # print(f"result of {request.function}:", res)
        return {
            "success": True,
            "message": f"Successfully submitted."
        }
    except Exception as e:
        # Return failure response
        return {
            "success": False,
            "message": f"Error executing {request.function}: {str(e)}"
        }

@app.get("/health-check")
async def health_check():
    return {"status": "READY"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=3011, reload=True)
