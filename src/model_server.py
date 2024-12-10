import threading
from cog.config import Config
from cog.server.http import create_app
import uvicorn
from cog.mode import Mode
import logging

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

def main():
    # inspect_logging_configuration()

    # Create a shutdown event for graceful shutdown
    shutdown_event = threading.Event()
    
    # Create the FastAPI application
    app = create_app(
        cog_config=Config(),
        shutdown_event=shutdown_event,
        app_threads=1,
        mode=Mode.PREDICT
    )
    
    # Configure and start the server
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=3009,
        log_level="info"
    )
    
    server = uvicorn.Server(config)
    # inspect_logging_configuration()
    server.run()

if __name__ == "__main__":
    main()
