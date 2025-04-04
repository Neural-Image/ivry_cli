from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import uvicorn
from typing import List, Dict, Any
import httpx
import asyncio
from functions import functions


class WorkflowInstance(BaseModel):
    id: str
    current_step: int
    function: str
    params: Dict[str, Any]
    webhook_url: str  # Add webhook URL to the model


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
async def send_to_webhook(instance: WorkflowInstance, results: Any):
    async with httpx.AsyncClient() as client:
        payload = {
            "workflow_run_id": instance.id,
            "current_step": instance.current_step,
            "results": results,
        }

        try:
            response = await client.post(instance.webhook_url, json=payload)
            response.raise_for_status()
            print(f"Webhook notification sent: {response.status_code}")
        except Exception as e:
            print(f"Failed to send webhook: {str(e)}")


# Background task handler
async def process_workflow_task(instance: WorkflowInstance):
    # Execute the function asynchronously
    results = await execute_function_async(instance.function, instance.params)

    # Send the results to the webhook
    await send_to_webhook(instance, results)


@app.post("/execute")
async def execute(instance: WorkflowInstance, background_tasks: BackgroundTasks):
    # Add the task to background tasks
    background_tasks.add_task(process_workflow_task, instance)

    # Return immediately with an acknowledgment
    return {
        "status": "success",
        "message": f"Workflow {instance.id} execution started",
        "workflow_run_id": instance.id,
    }


@app.get("/health-check")
async def health_check():
    return {"status": "READY"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=3011, reload=True)
