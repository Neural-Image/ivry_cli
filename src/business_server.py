from fastapi import FastAPI, File, UploadFile, Request, Response, HTTPException
from fastapi.staticfiles import StaticFiles
import uvicorn
import os
import json

from typing import Annotated
import httpx


import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('business_server')

def main():
    # Initialize the FastAPI app
    server = FastAPI()

    # Mount the static directory for serving files
    server.mount("/upload", StaticFiles(directory="upload"), name="upload")


    # Create the static directory if it doesn't exist
    os.makedirs("upload", exist_ok=True)


    # Add an API endpoint for file upload
    # @server.put("/upload/{file_path}")
    # async def upload_file(file: UploadFile = File(...)):
    #     """
    #     Upload a file and save it to the static directory.
    #     """
    #     file_location = f"upload/{file.filename}"
    #     with open(file_location, "wb") as f:
    #         f.write(await file.read())
    #     return {"message": "File uploaded successfully", "file_path": f"/static/{file.filename}"}
    
    @server.put("/upload_file/{file_path}")
    async def upload_file(file_path: str, request: Request, response: Response):
        """
        Handle file upload via PUT request and save to the static directory.
        """
        file_location = os.path.join("upload", file_path)
        try:
            # Read the entire body content
            file_content = await request.body()

            # Write the content to the specified file location
            with open(file_location, "wb") as file:
                file.write(file_content)

        except Exception as e:
            logger.error(f"Failed to save file: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

        logger.info(f"File saved successfully: {file_location}")
        # logger.info(f"prediction_id: {request.headers['X-Prediction-ID']}")

        response.headers["location"] = f"/upload/{file_path}"
        return {"message": "File uploaded successfully", "file_path": f"/static/{file_path}"}
    
    @server.post("/post_exp")
    async def upload_file(request: Request):
        return await request.json()

    @server.post("/webhook/prediction")
    async def prediction_webhook(request: Request):
        # Parse the incoming request body
        payload = await request.json()
        
        # Log the event (for debugging purposes)
        logger.info(f"Received webhook event: {json.dumps(payload, indent=4)}")
        
        # Extract necessary information
        event_type = payload.get("status")  # E.g., "starting", "completed"
        prediction_id = payload.get("id")
        logs = payload.get("logs")
        output = payload.get("output")

        # If the event type is "succeeded", make a request to localhost:3009/health-check
        # if event_type == "succeeded":
        #     time.sleep(30)
        #     async with httpx.AsyncClient() as client:
        #         response = await client.get("http://localhost:3009/health-check")
        #         # Print or log the response
        #         logger.info(f"Health-check response: {response.text}")        
        
        # Return a success response
        return {"message": "Webhook received successfully"}



    # Configure and run the server
    config = uvicorn.Config(
        server,
        host="0.0.0.0",
        port=3010,
        log_level="info"
    )

    server = uvicorn.Server(config)
    server.run()

if __name__ == "__main__":
    main()