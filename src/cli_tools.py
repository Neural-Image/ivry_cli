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
from util import get_apikey
import subprocess
import signal

#save to current dir
IVRY_CREDENTIAL_DIR = Path.home() / ".ivry"
IVRY_UPLOAD_URL = "https://test.ivry.co/pc/client-api/predict_signature/"
# only use predict.py
IVRY_PREDICT_FILE = "predict.py"


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
            parse_predict(predict_path / IVRY_PREDICT_FILE,"json")
        print("generating predict_signature.json")
        headers = {
        'X-API-KEY': str(apikey),
        'Content-Type': 'application/json',
        }
        url = "https://test.ivry.co/pc/client-api/predict_signature/" + str(model_id)
        with open("./predict_signature.json", "r") as json_file:
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
        url = "https://test.ivry.co/pc/client-api/predict_signature/"
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
        with open("client.log", "w") as log_file:
            p_cf = subprocess.Popen(
                ["project-x", "start", "model","--upload-url=https://test.ivry.co/pc/client-api/upload"],
                # ["project-x", "start", "model", "--upload_url", ""],
                stdout=log_file,
                stderr=subprocess.STDOUT  # Redirect stderr to the same log file
            )
        print("client is running. Logs are being written to client.log.")

        with open("cloudflare.log", "w") as log_file:
            p_cf = subprocess.Popen(
                ["cloudflared", "tunnel", "--config", "tunnel_config.json", "run"],
                stdout=log_file,
                stderr=subprocess.STDOUT  # Redirect stderr to the same log file
            )
        print("cloudflare is running. Logs are being written to cloudflare.log.")

    def stop_server(self):
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
        url = "https://test-pc.neuralimage.net/pc/client-api/models"
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
            start_model_server(parse_args(args_list))
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


def main():
    fire.Fire(Cli)
