import fire
import os
from pathlib import Path
from pydantic import BaseModel, Field
from business_server import main as start_business_server
from model_server import main as start_model_server_
from parse_InOut import parse_predict
from cog.server.http import parse_args, main as start_model_server
from communicate import upload_config
import requests
import json
import shutil
from util import get_apikey, find_comfyui_processes, get_comfyui_install_path, get_comfyui_ports
import subprocess
import signal
from heartbeat import HeartbeatManager
from websocket_comfyui import create_predict

#save to current dir
IVRY_CREDENTIAL_DIR = Path.home() / ".ivry"
IVRY_URL = "https://www.ivry.co/"
# only use predict.py
IVRY_PREDICT_FILE = "predict.py"
_heartbeat_manager = None

class Cli:
    def init_app(self, project_name: str, mode: str = "comfyui"):
        # Add project_name to name the init project
        src_path = Path(__file__).parent / "templates"
        dest_path = Path.cwd() / project_name
        # create new dir for init project
        if not dest_path.exists():
            dest_path.mkdir(parents=True, exist_ok=True)
            print(f"Directory {dest_path} created.")
        else:
            print(f"Directory {dest_path} already exists.")
             
        if mode == "comfyui":
            shutil.copy(src_path / "predict_comfyui.py", dest_path / "predict.py")
            shutil.copy(src_path / "cog.yaml", dest_path / "cog.yaml")
        elif mode == "model":
            # Add model template predict.py
            shutil.copy(src_path / "predict.py", dest_path / "predict.py")
            shutil.copy(src_path / "cog.yaml", dest_path / "cog.yaml")
        else:
            raise ValueError(f"mode {mode} is unknown.")
        return "Initialized."
    
    def login(self, auth_token: str):
        # TODO verify the auth_token is valid...
        os.makedirs(IVRY_CREDENTIAL_DIR, exist_ok=True)
        with open(IVRY_CREDENTIAL_DIR / "token.txt", "w", encoding="utf-8") as f:
            f.write(str(auth_token))
        return f"Token saved in {IVRY_CREDENTIAL_DIR / 'token.txt'}"
    
    def update_app(self, model_id: str, model_name: str = ''):
        # call fucntion in parse_InOut.py to parse predict.py to obtain predict_signature json
        apikey = get_apikey()
        predict_path = Path.cwd() / model_name
        tmp = predict_path / IVRY_PREDICT_FILE
        if not tmp.exists():
            raise Exception("Sorry, you need to init the project first.")
        else:
            signature_path = predict_path / "predict_signature.json"
            if not signature_path.exists():
                parse_predict(predict_path / IVRY_PREDICT_FILE,"json")
        print("generating predict_signature.json")
        headers = {
        'X-API-KEY': str(apikey),
        'Content-Type': 'application/json',
        }
        url = IVRY_URL + "pc/client-api/predict_signature/" + str(model_id)

        with open(signature_path, "r") as json_file:
            data = json.load(json_file)
        payload = json.dumps(data, indent=4)
        
        # call endpoint:/pc/client-api/predict_signature/{id}, to update json        
        response = requests.request("POST", url, headers=headers, data=payload)
        json_data = response.json()
        print(json_data.get("httpStatus"))
        print(json_data.get("data"))
    

    def upload_app(self, model_name: str = ''):
        # read token.txt
        # Reading the file
        
        apikey = get_apikey()
        print(f"Auth token: {apikey}")
        predict_path = Path.cwd() / model_name
        tmp = predict_path / IVRY_PREDICT_FILE
        if not tmp.exists():
            raise Exception("Sorry, you need to init the project first.")
        else:
        # call fucntion in parse_InOut.py to parse predict.py to obtain predict_signature json
            parse_predict(predict_path / IVRY_PREDICT_FILE,"json")
        print("generating predict_signature.json")
        # call function in docs/workflow_test/python/predict_signature.py, update json
        #页面获取

        headers = {
        'X-API-KEY': str(apikey),
        'Content-Type': 'application/json',
        }
        url = IVRY_URL + "pc/client-api/predict_signature/"
        with open("./predict_signature.json", "r") as json_file:
            data = json.load(json_file)
        payload = json.dumps(data, indent=4)
        response = requests.request("POST", url, headers=headers, data=payload)
        json_data = response.json()
        print(json_data.get("httpStatus"))
        # refer to docs/workflow_test/doc.md, save crediential and config to two separate json files at IVRY_CREDENTIAL_DIR
        IVRY_CREDENTIAL_DIR.mkdir(parents=True, exist_ok=True)
        credential = json_data["data"]["credential"]
        config = json_data["data"]["config"]
        # TMP: add token to config
        # Replace "tunnel" key with "token" and update its value
        config["token"] = credential["token"]  # Add the new key with the updated value
        del config["tunnel"]  # Remove the old "tunnel" key 

        # Save `credential` as a JSON file
        credential_file = predict_path / "tunnel_credential.json"
        with open(credential_file, "w") as file:
            json.dump(credential, file, indent=4)

        # Save `config` as a JSON file
        config_file = predict_path / "tunnel_config.json"
        with open(config_file, "w") as file:
            json.dump(config, file, indent=4)

        print(f"Credential saved to: {credential_file}")
        print(f"Config saved to: {config_file}")
    
    
    def start_server(self):
        global _heartbeat_manager
        
        # try:
        #     with open("tunnel_credential.json", "r") as f:
        #         config = json.load(f)
        #         model_id = config.get("TunnelName")
        # except (FileNotFoundError, json.JSONDecodeError):
        #     model_id = None
        model_id = None
            
        
        with open("client.log", "w") as log_file:
            p_cf = subprocess.Popen(
                ["project-x", "start", "model",f"--upload-url=http://localhost:3000/api/cli/upload"],
                # ["project-x", "start", "model", "--upload_url", ""],
                stdout=log_file,
                stderr=subprocess.STDOUT  # Redirect stderr to the same log file
            )
        print("client is running. Logs are being written to client.log.")

        # with open("cloudflare.log", "w") as log_file:
        #     p_cf = subprocess.Popen(
        #         ["cloudflared", "tunnel", "--config", "tunnel_config.json", "run"],
        #         stdout=log_file,
        #         stderr=subprocess.STDOUT  # Redirect stderr to the same log file
        #     )
        # print("cloudflare is running. Logs are being written to cloudflare.log.")

        try:
            if model_id:
                apikey = get_apikey()
                upload_url = f"{IVRY_URL}pc/client-api/heartbeat"
                
                # 停止旧的心跳管理器（如果存在）
                if _heartbeat_manager:
                    _heartbeat_manager.stop()
                    
                # 创建并启动新的心跳管理器
                _heartbeat_manager = HeartbeatManager(
                    upload_url=upload_url,
                    model_id=model_id,
                    api_key=apikey,
                    interval=heartbeat_interval
                )
                _heartbeat_manager.start()
                print(f"Heartbeat service started with interval of {heartbeat_interval} seconds")
        except Exception as e:
            print(f"Error starting heartbeat service: {e}")


    def stop_server(self):
        global _heartbeat_manager
        if _heartbeat_manager:
            _heartbeat_manager.stop()
            _heartbeat_manager = None
            print("Heartbeat service stopped")
    # Helper function to terminate a process by its name
        def terminate_process(name):
            try:
                # List all processes and find those matching the name
                result = subprocess.run(["pgrep", "-f", name], stdout=subprocess.PIPE, text=True)
                pids = result.stdout.strip().split("\n")
                if pids:
                    for pid in pids:
                        os.kill(int(pid), signal.SIGTERM)
                    print(f"Terminated {name} processes with PIDs: {', '.join(pids)}")
                else:
                    print(f"No processes found for {name}")
            except Exception as e:
                print(f"Error stopping {name}: {e}")

        # Terminate `project-x` process
        terminate_process("project-x start model")

        # Terminate `cloudflared` process
        terminate_process("cloudflared tunnel --config tunnel_config.json run")
        
        print("All server processes have been stopped.")



    def list_models(self):
        # call endpoint:/pc/client-api/models, return model information ids.
        apikey = get_apikey()
        headers = {
        'X-API-KEY': str(apikey),
        'Content-Type': 'application/json',
        }
        url = IVRY_URL + "pc/client-api/models"
        response = requests.request("POST", url, headers=headers)
        json_data = response.json()
        print(json_data.get("httpStatus"))
        print(json.dumps(json_data.get("data"), indent=4))

    def retrieve_tunnel_credential(self):
        with open(IVRY_CREDENTIAL_DIR / "token.txt") as f:
            token = f.read()
        res = requests.get(
            "http://52.53.132.109:8083/pc/client-api/upload/credential",
            headers={
                'Authorization': f'Bearer {token}'
            })
        res.raise_for_status()
        credential = json.loads(res.content.decode('utf-8'))['data']
        os.makedirs(IVRY_CREDENTIAL_DIR, exist_ok=True)
        save_path = IVRY_CREDENTIAL_DIR / "tunnel_credential.json"
        with open(save_path, 'w') as file:
            json.dump(credential, file, indent=4)  # Pretty-print with indent=4        
        return f"Credential saved at {save_path}."
    
    def retrieve_tunnel_config(self):
        raise NotImplementedError("Not implemented yet.")
    
    def turn_on_tunnel(self):
        # notebook/comfyui_colab.ipynb
        raise NotImplementedError("Not implemented yet.")

    def start(self, server: str, **kwargs):
        if server == "model":
            args_list = []
            for key, value in kwargs.items():
                if isinstance(value, bool) and value:
                    args_list.append(f"--{key}")
                else:
                    args_list.extend([f"--{key}", str(value)])  # Separate key and value
            start_model_server_(parse_args(args_list))
            # start_model_server_()
        if server == "business":
            start_business_server()
        else:
            raise ValueError(f"server {server} is unknown.")

    def parse_predict(self, predict_filename: str = "predict.py"):
        parse_predict(predict_filename)
        return f"Created predict_signature.yaml."

    def upload_config(self):
        upload_config()
        return f"Config Uploaded."

    def find_comfyUI(self):
        proc = find_comfyui_processes()
        if not proc:
            print("didn't detect ComfyUI process")
        else:
            pid = proc.pid
            name = proc.info.get('name') or ''
            port = get_comfyui_ports(proc)
            path = get_comfyui_install_path(proc)
            print(f"detected ComfyUI process: PID={pid}, name={name}")
            print(f"  comfyUI install path: {path if path else 'nothing detected'}")
            print(f"  listning port: {port if port else 'nothing detected'}")


    def get_heartbeat_status(self):
        """获取心跳状态"""
        global _heartbeat_manager
        
        if _heartbeat_manager:
            return _heartbeat_manager.get_status()
        return {"running": False, "message": "Heartbeat service not started"}


    def pull_project(self, project_id: str, project_name: str = None):
        """
        Pull a project from the backend by its ID.
        
        This command retrieves a project configuration from the server, including:
        - predict.py file content
        - signature JSON
        - CloudFlare tunnel configuration
        
        It then creates a local project directory with all necessary files.
        
        Args:
            project_id: The ID of the project to pull
            project_name: Optional name for the local project directory (defaults to project_id if not provided)
        
        Returns:
            str: Status message
        """
        # Use the provided project name or default to project_id
        local_name = project_name or project_id
        
        # Get API key for authentication
        apikey = get_apikey()
        
        # Set up headers for the request
        headers = {
            'X-API-KEY': str(apikey),
            'Content-Type': 'application/json',
        }
        
        # Construct the URL for the API endpoint
        url = f"{IVRY_URL}pc/client-api/projects/{project_id}/pull"
        
        try:
            # Make the request to pull the project
            print(f"Pulling project {project_id} from server...")
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise an exception for HTTP errors
            
            project_data = response.json()
            
            if project_data.get("httpStatus") != 200:
                return f"Error: {project_data.get('message', 'Unknown error occurred')}"
            
            project_data = project_data.get("data", {})
            
            # Create the project directory
            dest_path = Path.cwd() / local_name
            if not dest_path.exists():
                dest_path.mkdir(parents=True, exist_ok=True)
                print(f"Directory {dest_path} created.")
            else:
                print(f"Directory {dest_path} already exists.")
            
            # Extract data from response
            signature_data = project_data.get("signature", {})
            tunnel_config = project_data.get("tunnelConfig", {})
            tunnel_credential = project_data.get("tunnelCredential", {})
            predict_content = create_predict()
            
            # Save the predict.py file
            with open(dest_path / "predict.py", "w", encoding="utf-8") as f:
                f.write(predict_content)
            print(f"predict.py saved to {dest_path}")
            
            # Save signature data as JSON
            if signature_data:
                with open(dest_path / "predict_signature.json", "w", encoding="utf-8") as f:
                    json.dump(signature_data, f, indent=4)
                print(f"predict_signature.json saved to {dest_path}")
            
            # Save tunnel configuration
            if tunnel_config:
                with open(dest_path / "tunnel_config.json", "w", encoding="utf-8") as f:
                    json.dump(tunnel_config, f, indent=4)
                print(f"tunnel_config.json saved to {dest_path}")
            
            # Save tunnel credentials
            if tunnel_credential:
                with open(dest_path / "tunnel_credential.json", "w", encoding="utf-8") as f:
                    json.dump(tunnel_credential, f, indent=4)
                print(f"tunnel_credential.json saved to {dest_path}")
            
            # Save cog.yaml
            with open(dest_path / "cog.yaml", "w", encoding="utf-8") as f:
                f.write('predict: "predict.py:Predictor"\n')
            print(f"cog.yaml saved to {dest_path}")
            
            return f"Project {project_id} successfully pulled to {local_name}/"
            
        except requests.exceptions.HTTPError as e:
            return f"HTTP Error: {str(e)}"
        except requests.exceptions.ConnectionError:
            return "Connection Error: Could not connect to the server. Please check your internet connection."
        except requests.exceptions.Timeout:
            return "Timeout Error: The request timed out. Please try again later."
        except requests.exceptions.RequestException as e:
            return f"Request Error: {str(e)}"
        except json.JSONDecodeError:
            return "Error: Invalid response received from server (not valid JSON)"
        except Exception as e:
            return f"Unexpected error: {str(e)}"



def main():
    fire.Fire(Cli)
