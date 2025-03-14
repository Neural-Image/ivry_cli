#This is an example that uses the websockets api to know when a prompt execution is done
#Once the prompt execution is done it downloads the images using the /history endpoint

import json
import urllib.request
import urllib.parse
import logging
import time
import traceback
import sys
import socket
import websocket


COMFYUI_CONNECTION_ERROR = "CLI_ERR_1001"  # Cannot connect to ComfyUI
COMFYUI_WEBSOCKET_ERROR = "CLI_ERR_1002"   # WebSocket connection failed
COMFYUI_PROCESSING_ERROR = "CLI_ERR_1101"  # Error during ComfyUI processing
COMFYUI_NO_OUTPUT = "CLI_ERR_1201"        # No output files generated

LOG_FILE = "client.log"
MIN_INTERVAL = 1  


def create_predict():
    pass


def queue_prompt(prompt, client_id, server_address):
    try:
        p = {"prompt": prompt, "client_id": client_id}
        data = json.dumps(p).encode('utf-8')
        req = urllib.request.Request("http://{}/prompt".format(server_address), data=data)
        return json.loads(urllib.request.urlopen(req).read())
    except Exception as e:
        logger = logging.getLogger("predict_logger")
        error_msg = f"Error queuing prompt: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        raise

def get_image(filename, subfolder, folder_type, server_address):
    try:
        data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        url_values = urllib.parse.urlencode(data)
        with urllib.request.urlopen("http://{}/view?{}".format(server_address, url_values)) as response:
            return response.read()
    except Exception as e:
        logger = logging.getLogger("predict_logger")
        error_msg = f"Error getting image {filename}: {str(e)}"
        logger.error(error_msg)
        raise

def get_history(prompt_id, server_address):
    try:
        with urllib.request.urlopen("http://{}/history/{}".format(server_address, prompt_id)) as response:
            return json.loads(response.read())
    except Exception as e:
        logger = logging.getLogger("predict_logger")
        error_msg = f"Error getting history for prompt {prompt_id}: {str(e)}"
        logger.error(error_msg)
        raise

def setup_logger():
    """Set up the logger with handlers for both file and console output"""
    logger = logging.getLogger("predict_logger")
    logger.setLevel(logging.INFO)
    
    # Check if handlers already exist to prevent duplicate handlers
    if not logger.handlers:
        # File handler
        file_handler = logging.FileHandler(LOG_FILE)
        file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(file_formatter)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = logging.Formatter("%(levelname)s: %(message)s")
        console_handler.setFormatter(console_formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    
    return logger

def check_comfyui_connection(server_address, timeout=5):
        """
        Check if we can connect to the ComfyUI server
        
        Args:
            server_address: ComfyUI server address in format host:port
            timeout: Connection timeout in seconds
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        # Parse hostname and port
        try:
            host, port_str = server_address.split(':')
            port = int(port_str)
        except ValueError:
            print(f"ERROR[{COMFYUI_CONNECTION_ERROR}]: Invalid server address format: {server_address}, should be 'host:port'")
            return False
        
        # Check TCP connection
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result != 0:
                print(f"ERROR[{COMFYUI_CONNECTION_ERROR}]:: Could not connect to {server_address}, port might be closed")
                return False
                
            # Try HTTP connection
            try:
                url = f"http://{server_address}/"
                conn = urllib.request.urlopen(url, timeout=timeout)
                if conn.getcode() != 200:
                    print(f"WARNING: ComfyUI server returned status code: {conn.getcode()}")
            except (urllib.error.URLError, ConnectionRefusedError) as e:
                print(f"WARNING: HTTP connection check failed: {e}")
                # Continue execution as some ComfyUI setups might block HTTP requests but still allow WebSocket
            
            # Try WebSocket connection
            try:
                ws_url = f"ws://{server_address}/ws"
                ws = websocket.create_connection(ws_url, timeout=timeout)
                ws.close()
                return True
            except Exception as e:
                print(f"ERROR[{COMFYUI_WEBSOCKET_ERROR}]: WebSocket connection failed: {e}")
                return False
                
        except Exception as e:
            print(f"ERROR: Exception during connection check: {e}")
            return False



def get_images(ws, client_id, prompt, server_address):
    logger = setup_logger()
    output_images = {}
    last_print_time = 0
    
    try:
        # Queue the prompt and get the prompt ID
        logger.info("Queuing prompt...")
        prompt_response = queue_prompt(prompt, client_id, server_address)
        prompt_id = prompt_response['prompt_id']
        logger.info(f"Prompt queued with ID: {prompt_id}")
        
        # Process execution messages
        execution_errors = []
        while True:
            try:
                out = ws.recv()
                current_time = time.time()
                
                if isinstance(out, str):
                    message = json.loads(out)
                    
                    # Only log messages at appropriate intervals to avoid spamming
                    if current_time - last_print_time >= MIN_INTERVAL:
                        logger.info(f"Received message: {message['type']}")
                        last_print_time = current_time
                    
                    # Check for execution status
                    if message['type'] == 'executing':
                        data = message['data']
                        if data['node'] is None and data['prompt_id'] == prompt_id:
                            break  # Execution is done
                    
                    # Check for error messages
                    if message['type'] == 'execution_error':
                        error_msg = f"Execution error in node {message.get('node_id', 'unknown')}: {message.get('exception_message', 'No details')}"
                        logger.error(error_msg)
                        execution_errors.append(error_msg)
                    
                    # Log progress updates
                    if message['type'] == 'progress':
                        if current_time - last_print_time >= MIN_INTERVAL:
                            logger.info(f"Progress: {message.get('value', 0):.2f}%")
                            last_print_time = current_time
                else:
                    # This is binary data (likely a preview image)
                    continue
                    
            except Exception as e:
                error_msg = f"Error processing websocket message: {str(e)}\n{traceback.format_exc()}"
                logger.error(error_msg)
                # Don't break the loop for individual message errors
        
        # Check if there were any execution errors
        if execution_errors:
            error_details = "\n".join(execution_errors)
            logger.error(f"ComfyUI execution failed with errors:\n{error_details}")
            raise RuntimeError(f"ComfyUI execution failed with {len(execution_errors)} errors: {error_details}")
        else:
            logger.info("Execution completed successfully")
        
        # Get history and process output images
        logger.info(f"Getting history for prompt {prompt_id}...")
        history = get_history(prompt_id, server_address)[prompt_id]
        
        for node_id in history['outputs']:
            
            node_output = history['outputs'][node_id]
            images_output = []
            print("node_output",node_output)
            if 'images' in node_output:
                for image in node_output['images']:
                    logger.info(f"Found output image: {image['filename']}")
                    if image['subfolder'] != "":
                        subfolder = image['subfolder']
                        images_output.append(subfolder + "/" + image['filename'])
                    else:
                        images_output.append(image['filename'])
            
            if 'gifs' in node_output:
                for image in node_output['gifs']:
                    logger.info(f"Found output gif: {image['filename']}")
                    if image['subfolder'] != "":
                        subfolder = image['subfolder']
                        images_output.append(subfolder + "/" + image['filename'])
                    else:
                        images_output.append(image['filename'])
            
            if 'videos' in node_output:
                for image in node_output['videos']:
                    logger.info(f"Found output video: {image['filename']}")
                    if image['subfolder'] != "":
                        subfolder = image['subfolder']
                        images_output.append(subfolder + "/" + image['filename'])
                    else:
                        images_output.append(image['filename'])
            
            if 'audios' in node_output:
                for image in node_output['audios']:
                    logger.info(f"Found output audios: {image['filename']}")
                    if image['subfolder'] != "":
                        subfolder = image['subfolder']
                        images_output.append(subfolder + "/" + image['filename'])
                    else:
                        images_output.append(image['filename'])
            
            if 'audio' in node_output:
                for image in node_output['audio']:
                    logger.info(f"Found output audio: {image['filename']}")
                    if image['subfolder'] != "":
                        subfolder = image['subfolder']
                        images_output.append(subfolder + "/" + image['filename'])
                    else:
                        images_output.append(image['filename'])
            
            output_images[node_id] = images_output
        
        logger.info(f"Processing complete. Found outputs for {len(output_images)} nodes.")
        return output_images
        
    except Exception as e:
        error_msg = f"Critical error in get_images: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)

        raise RuntimeError(f"ComfyUI processing failed: {str(e)}")