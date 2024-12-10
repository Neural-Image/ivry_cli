from fastapi import FastAPI, File, UploadFile, Request
from fastapi.staticfiles import StaticFiles
import uvicorn
import os
import json
import logging

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
    @server.put("/upload")
    async def upload_file(file: UploadFile = File(...)):
        """
        Upload a file and save it to the static directory.
        """
        file_location = f"upload/{file.filename}"
        with open(file_location, "wb") as f:
            f.write(await file.read())
        return {"message": "File uploaded successfully", "file_path": f"/static/{file.filename}"}

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