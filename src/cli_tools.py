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
import platform
from heartbeat import HeartbeatManager
from websocket_comfyui import create_predict
from pull_project import generate_predict_file
from find_comfyui_path import find_comfyui_path_by_port
try:
    import supervisor.supervisord
    import supervisor.options
    import supervisor.xmlrpc
    SUPERVISOR_AVAILABLE = True
except ImportError:
    SUPERVISOR_AVAILABLE = False


#save to current dir
IVRY_CREDENTIAL_DIR = Path.home() / ".ivry"
#IVRY_URL = "https://www.ivry.co/"
IVRY_URL = "https://www.lormul.org/"
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
        
        try:
            with open("tunnel_credential.json", "r") as f:
                config = json.load(f)
                model_id = config.get("TunnelName")
        except (FileNotFoundError, json.JSONDecodeError):
            model_id = None
            
        
        with open("client.log", "w") as log_file:
            p_cf = subprocess.Popen(
                ["project-x", "start", "model",f"--upload-url={IVRY_URL}pc/client-api/upload"],
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


    def pull_project(self, app_id: str, comfyui_port: str = "8188", project_name: str = None, comfyUI_dir: str = None):
        """
        从服务器拉取应用配置并创建本地项目目录
        
        此命令从服务器检索应用配置信息，包括：
        - 配置相关数据
        - CloudFlare 隧道配置
        
        然后在本地创建项目目录并保存所有必要的文件
        
        参数:
            app_id: 要拉取的应用ID
            project_name: 可选的本地项目目录名称（如果不提供则默认使用app_id）
        
        返回:
            str: 状态消息
        """
        # 使用提供的项目名称或默认为app_id
        
        
        # 获取API密钥进行认证
        apikey = get_apikey()
        
        # 设置请求头
        headers = {
            'X-API-KEY': str(apikey),
            'Content-Type': 'application/json',
        }
        project_dir = Path("ivry_project/comfyUI_project")
        project_dir.mkdir(parents=True, exist_ok=True)
        try:
            # 构建API URL
            url = f"{IVRY_URL}api/cli/app/{app_id}"
            
            # 发起请求拉取应用配置
            print(f"正在从服务器拉取应用 {app_id} 的配置...")
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # 对HTTP错误抛出异常
            
            data = response.json()
            
            if data.get("success") != True:
                return f"错误: {data.get('message', '发生未知错误')}"
            
            app_config = data.get("data", {})
            local_name = "app_" + str(app_id)
            project_path = project_dir / local_name
            # 创建项目目录
            dest_path = Path.cwd() / str(project_path)
            if not dest_path.exists():
                dest_path.mkdir(parents=True, exist_ok=True)
                print(f"目录 {dest_path} 已创建。")
            else:
                print(f"目录 {dest_path} 已存在。")
            
            # 保存配置数据为JSON
            tunnel_config = data["tunnelCfg"]["config"]
            tunnel_credential = data["tunnelCfg"]["credential"]
            
            
            if tunnel_config:
                with open(project_path / "tunnel_config.json", "w", encoding="utf-8") as f:
                    json.dump(tunnel_config, f, indent=4, ensure_ascii=False)
                print(f"app_config.json 已保存到 {dest_path}")
            
            if tunnel_credential:
                with open(project_path / "tunnel_credential.json", "w", encoding="utf-8") as f:
                    json.dump(tunnel_credential, f, indent=4, ensure_ascii=False)
                print(f"tunnel_config.json 已保存到 {dest_path}")
            if comfyUI_dir == None:
                comfyUI_dir = find_comfyui_path_by_port(int(comfyui_port))
            if not comfyUI_dir:
                return ("error: cannot find your running comfyUI process " + 
                        f"{comfyui_port} 上。\n" +
                        "if your comfyUI process is running, you could add it to the command。like: ivry_cli pull_project 66 --comfyui_port 8188 --comfyUI_dir /path/to/comfyUI")
            # 根据配置数据创建必要的预测器文件
            system_name = platform.system().lower()

            generate_predict_file(dir_comfyui=comfyUI_dir,port_comfyui=comfyui_port,input_section=data,os_system=system_name,workflow_name=local_name)
        
            # 这部分取决于您的具体应用设计，可能需要根据实际情况调整
            source_path = "predict.py"  # 当前目录下的 predict.py
            destination_path = str(project_path) + "/predict.py"  # 目标目录
            shutil.move(source_path, destination_path)
            shutil.copy("src/templates/cog.yaml", str(project_path) + "/cog.yaml")
            
            return f"应用 {app_id} 已成功拉取到 {local_name}/ 目录"
            
        except requests.exceptions.HTTPError as e:
            return f"HTTP 错误: {str(e)}"
        except requests.exceptions.ConnectionError:
            return "连接错误: 无法连接到服务器。请检查您的网络连接。"
        except requests.exceptions.Timeout:
            return "超时错误: 请求超时。请稍后重试。"
        except requests.exceptions.RequestException as e:
            return f"请求错误: {str(e)}"
        except json.JSONDecodeError:
            return "错误: 从服务器收到的响应无效（非有效JSON）"
        except Exception as e:
            return f"意外错误: {str(e)}"


    def list_apps(self):
        """
        Retrieves and displays a list of all applications for the current user.
        
        This function calls the '/api/cli/apps/list' endpoint to fetch all apps
        associated with the user's API key and displays them in a formatted way.
        
        Returns:
            str: A message indicating the result of the operation
        """
        try:
            # Get the API key for authentication
            apikey = get_apikey()
            
            # Set up request headers
            headers = {
                'X-API-KEY': str(apikey),
                'Content-Type': 'application/json',
            }
            
            # Construct the API URL
            url = IVRY_URL + "api/cli/apps/list"
            
            # Make the request to retrieve all apps
            print("Retrieving applications list...")
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise an exception for HTTP errors
            
            # Parse the JSON response
            json_data = response.json()
            # Check if the request was successful
            if json_data.get("success") == True:
                apps = json_data.get("apps", [])
                
                if not apps:
                    return "No applications found for your account."
                
                # Format and display the apps information
                print("Applications retrieved successfully!\n")
                print("=" * 80)
                print(f"{'ID':<15} {'Name':<25} {'isPublic':<15} {'state':<15} {'Created Date'}")
                print("-" * 80)
                
                for app in apps:
                    app_id = app.get("id", "N/A")
                    name = app.get("name", "N/A")
                    app_type = app.get("isPublic", "N/A")
                    status = app.get("state", "N/A")
                    created_date = app.get("createdAt", "N/A")
                    
                    print(f"{app_id:<15} {name:<25} {app_type:<15} {status:<15} {created_date}")
                
                print("=" * 80)
                return f"Retrieved {len(apps)} applications."
            else:
                return f"Error: {json_data.get('message', 'An unknown error occurred')}"
        
        except requests.exceptions.HTTPError as e:
            return f"HTTP Error: {str(e)}"
        except requests.exceptions.ConnectionError:
            return "Connection Error: Unable to connect to the server. Please check your network connection."
        except requests.exceptions.Timeout:
            return "Timeout Error: The request timed out. Please try again later."
        except requests.exceptions.RequestException as e:
            return f"Request Error: {str(e)}"
        except json.JSONDecodeError:
            return "Error: Invalid response received from the server (not valid JSON)"
        except Exception as e:
            return f"Unexpected error: {str(e)}"


    def run_server(self, project_path: str = None, detached: bool = False, force: bool = False, background: bool = False):
        """
        Start the ivry_cli model server and cloudflared tunnel using PM2
        
        This function uses PM2 to manage and monitor the ivry_cli model server and cloudflared tunnel processes
        
        Args:
            project_path (str, optional): Path to the project directory. If not provided,
                                        uses the current working directory.
            detached (bool, optional): If True, runs the servers in detached mode (background).
                                    Default is False.
            force (bool, optional): If True, forcibly restart services even if they're already running.
                                    Default is False.
            background (bool, optional): If True, run with nohup in the background. Default is False.
        
        Returns:
            str: A message indicating the result of the operation
        """
        try:
            # 检查PM2是否已安装
            import subprocess
            result = subprocess.run(["pm2", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                return "错误: PM2未安装。请使用'npm install -g pm2'安装PM2。"
        except FileNotFoundError:
            return "错误: 未找到PM2。请使用'npm install -g pm2'安装PM2。"
        
        # 确定项目目录
        if project_path:
            project_dir = Path(project_path)
        else:
            project_dir = Path.cwd()
        
        # 验证项目目录存在并包含所需文件
        if not project_dir.exists():
            return f"错误: 项目目录'{project_dir}'不存在。"
        
        tunnel_config = project_dir / "tunnel_config.json"
        if not tunnel_config.exists():
            return f"错误: 在'{project_dir}'中找不到tunnel_config.json。确保这是有效的ivry项目目录。"
        
        # 创建日志目录（如果不存在）
        logs_dir = project_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        
        # 生成PM2配置文件
        pm2_config_path = project_dir / "pm2_config.json"
        
        # 获取model_id（用于标识和日志）
        try:
            with open(tunnel_config, "r") as f:
                config = json.load(f)
                model_id = config.get("tunnel") or config.get("token") or "unknown"
        except (json.JSONDecodeError, FileNotFoundError):
            model_id = "unknown"
        
        # 检查ivry服务器端口是否已被使用
        import socket
        def check_port(port):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind(('127.0.0.1', port))
                s.close()
                return False  # 端口未被占用
            except socket.error:
                return True  # 端口已被占用
        
        # ivry服务器通常使用3009端口
        if check_port(3009) and not force:
            return ("Port 3009 is already in use, which will prevent ivry_server from starting.\n"
                "Please stop any existing ivry_server instances first or use --force to attempt restart.")
        
        # 检查是否已有PM2实例在运行相同的应用
        result = subprocess.run(["pm2", "list"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if "ivry_server" in result.stdout or "cloudflared_tunnel" in result.stdout:
            if not force:
                return ("PM2已经在运行ivry服务。\n"
                    "要查看状态：ivry_cli pm2_status\n"
                    "要重启：ivry_cli pm2_control restart\n"
                    "要强制启动新实例：ivry_cli run_server --force")
            else:
                # 强制模式：先停止现有进程
                subprocess.run(["pm2", "delete", "ivry_server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                subprocess.run(["pm2", "delete", "cloudflared_tunnel"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # 日志文件路径
        ivry_log_file = (logs_dir / "ivry_server.log").resolve()
        cloudflared_log_file = (logs_dir / "cloudflared.log").resolve()
        
        # 创建PM2配置
        # Create PM2 configuration
        pm2_config = {
            "apps": [
                {
                    "name": "ivry_server",
                    "interpreter": "python",  # Specify the interpreter
                    "script": shutil.which("ivry_cli"),  # Use the full path to the ivry_cli executable
                    "args": ["start", "model", f"--upload-url={IVRY_URL}api/cli/upload"],
                    "cwd": str(project_dir),
                    "log_date_format": "YYYY-MM-DD HH:mm:ss Z",
                    "output": str(ivry_log_file),
                    "error": str(ivry_log_file),
                    "merge_logs": True,
                    "autorestart": True,
                    "env": {
                        "PM2_HOME": str(project_dir / ".pm2")
                    }
                },
                # cloudflared configuration remains unchanged
                {
                    "name": "cloudflared_tunnel",
                    "script": "cloudflared",
                    "args": ["tunnel", "--config", "tunnel_config.json", "run"],
                    "cwd": str(project_dir),
                    "log_date_format": "YYYY-MM-DD HH:mm:ss Z",
                    "output": str(cloudflared_log_file),
                    "error": str(cloudflared_log_file),
                    "merge_logs": True,
                    "autorestart": True,
                    "env": {
                        "PM2_HOME": str(project_dir / ".pm2")
                    }
                }
            ]
        }
        
        # 写入PM2配置
        with open(pm2_config_path, "w") as f:
            json.dump(pm2_config, f, indent=4)
        
        print(f"Starting ivry_cli model server and cloudflared tunnel for project at: {project_dir}")
        print(f"Model ID: {model_id}")
        print(f"Logs will be written to: {logs_dir}")
        
        try:
            # 启动PM2
            subprocess.run(["pm2", "start", str(pm2_config_path)], check=True)
            
            # 保存PM2配置以便重启后自动恢复
            subprocess.run(["pm2", "save"], check=True)
            
            # 启动心跳服务（如果model_id可用）
            # if model_id and model_id != "unknown":
            #     try:
            #         global _heartbeat_manager
            #         apikey = get_apikey()
            #         upload_url = f"{IVRY_URL}pc/client-api/heartbeat"
                    
            #         # 停止现有的心跳管理器
            #         if _heartbeat_manager:
            #             _heartbeat_manager.stop()
                    
            #         # 启动新的心跳管理器
            #         _heartbeat_manager = HeartbeatManager(
            #             upload_url=upload_url,
            #             model_id=model_id,
            #             api_key=apikey,
            #             interval=3600  # 默认1小时间隔
            #         )
            #         _heartbeat_manager.start()
            #         print("Heartbeat service started")
            #     except Exception as e:
            #         print(f"警告: 启动心跳服务失败: {e}")
            
            return (f"Services started with PM2.\n"
                f"To view status: ivry_cli pm2_status\n"
                f"To control services: ivry_cli pm2_control [start|stop|restart]\n"
                f"To view logs: ivry_cli pm2_logs\n"
                f"To stop all services: ivry_cli stop_server")
        
        except subprocess.CalledProcessError as e:
            return f"使用PM2启动服务时出错: {str(e)}"
        except Exception as e:
            return f"启动服务时发生错误: {str(e)}"

    def stop_server(self, project_path: str = None, force: bool = False):
        """
        Stop all ivry services managed by PM2.
        
        Args:
            project_path (str, optional): Path to the project directory. If not provided,
                                        uses the current working directory.
            force (bool, optional): If True, forcibly stop all processes. Default is False.
        
        Returns:
            str: Status information about the stop operation
        """
        try:
            # 确定项目目录
            if project_path:
                project_dir = Path(project_path)
            else:
                project_dir = Path.cwd()
            
            # 停止心跳管理器
            global _heartbeat_manager
            if _heartbeat_manager:
                _heartbeat_manager.stop()
                _heartbeat_manager = None
                print("Heartbeat service stopped")
            
            # 使用PM2停止服务
            import subprocess
            
            result = subprocess.run(["pm2", "list"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if "ivry_server" not in result.stdout and "cloudflared_tunnel" not in result.stdout:
                return "No running ivry services found."
            
            try:
                # 停止并删除ivry_server
                subprocess.run(["pm2", "delete", "ivry_server"], check=not force)
            except subprocess.CalledProcessError:
                if not force:
                    return "停止ivry_server失败。尝试使用--force参数。"
            
            try:
                # 停止并删除cloudflared_tunnel
                subprocess.run(["pm2", "delete", "cloudflared_tunnel"], check=not force)
            except subprocess.CalledProcessError:
                if not force:
                    return "停止cloudflared_tunnel失败。尝试使用--force参数。"
            
            # 保存PM2配置
            subprocess.run(["pm2", "save"], check=False)
            
            # Verify processes are actually stopped by checking system processes
            ps_result = subprocess.run(["ps", "aux"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            ivry_running = "ivry_cli start model" in ps_result.stdout
            cloudflared_running = "cloudflared tunnel" in ps_result.stdout
            
            if ivry_running or cloudflared_running:
                if force:
                    # In force mode, attempt to kill processes directly
                    self._force_kill_processes()
                    return "All ivry services have been forcibly terminated."
                else:
                    return "Some ivry processes are still running. Use --force to terminate them."
            
            return "All ivry services have been successfully stopped."
        
        except FileNotFoundError:
            return "错误: PM2未安装或未找到。请确保安装了PM2。"
        except Exception as e:
            if force:
                # 在强制模式下尝试使用系统命令终止进程
                try:
                    self._force_kill_processes()
                    return "已强制终止所有ivry相关进程。"
                except Exception as kill_error:
                    return f"错误: 无法停止服务: {str(e)}。强制终止也失败: {str(kill_error)}"
            return f"错误: 停止服务时发生错误: {str(e)}"

    def _force_kill_processes(self):
        """尝试强制终止ivry相关进程"""
        import subprocess
        import os
        import signal
        
        # 终止进程的辅助函数
        def terminate_process(name):
            try:
                # 列出所有进程并找到匹配名称的进程
                result = subprocess.run(["pgrep", "-f", name], stdout=subprocess.PIPE, text=True)
                pids = [pid.strip() for pid in result.stdout.strip().split("\n") if pid.strip()]
                
                if pids:
                    for pid in pids:
                        try:
                            os.kill(int(pid), signal.SIGTERM)
                        except ProcessLookupError:
                            continue
                    print(f"已终止{name}进程，PID: {', '.join(pids)}")
            except Exception as e:
                print(f"停止{name}时出错: {e}")
        
        # 终止`ivry_cli`进程
        terminate_process("ivry_cli start model")
        
        # 终止`cloudflared`进程
        terminate_process("cloudflared tunnel")
        
        # 终止PM2进程
        terminate_process("pm2")
        
        # 终止3009端口上的进程
        def kill_process_by_port(port):
            try:
                result = subprocess.run(
                    ["lsof", "-t", f"-i:{port}"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                pids = [pid for pid in result.stdout.strip().split("\n") if pid]
                
                for pid in pids:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                    except ProcessLookupError:
                        continue
            except Exception:
                pass
        
        # 终止3009端口上的进程
        kill_process_by_port(3009)

    def pm2_status(self, project_path: str = None):
        """
        Display the status of ivry services managed by PM2.
        
        Args:
            project_path (str, optional): Path to the project directory. If not provided,
                                        uses the current working directory.
        
        Returns:
            str: Status information of PM2-managed processes
        """
        try:
            # 确定项目目录
            if project_path:
                project_dir = Path(project_path)
            else:
                project_dir = Path.cwd()
            
            # 检查PM2是否已安装
            import subprocess
            result = subprocess.run(["pm2", "list"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                return "错误: 无法获取PM2状态。确保PM2已安装并正常运行。"
            
            # 格式化并返回状态信息
            return f"PM2进程状态:\n\n{result.stdout}"
        
        except FileNotFoundError:
            return "错误: PM2未安装或未找到。请确保安装了PM2。"
        except Exception as e:
            return f"获取PM2状态时出错: {str(e)}"

    def pm2_control(self, command: str, process: str = "all", project_path: str = None):
        """
        控制PM2管理的ivry服务。
        
        参数:
            command (str): 控制命令 ('start', 'stop', 'restart', 'reload')
            process (str, optional): 要控制的进程 ('ivry_server', 'cloudflared_tunnel', 或 'all')。
                                    默认为 'all'。
            project_path (str, optional): 项目目录路径。如果未提供，使用当前工作目录。
        
        返回:
            str: 控制操作的结果
        """
        try:
            # 验证命令
            if command not in ["start", "stop", "restart", "reload"]:
                return f"错误: 无效的命令 '{command}'。使用 'start', 'stop', 'restart' 或 'reload'。"
            
            # 验证进程
            valid_processes = ["all", "ivry_server", "cloudflared_tunnel"]
            if process not in valid_processes:
                return f"错误: 无效的进程 '{process}'。有效选项: {', '.join(valid_processes)}"
            
            # 确定项目目录
            if project_path:
                project_dir = Path(project_path)
            else:
                project_dir = Path.cwd()
            
            # 检查PM2是否已安装
            import subprocess
            
            # 执行命令
            if process == "all":
                if command == "start":
                    # 检查配置文件
                    pm2_config_path = project_dir / "pm2_config.json"
                    if not pm2_config_path.exists():
                        return f"错误: 找不到PM2配置文件。请先运行 'ivry_cli run_server'。"
                    
                    result = subprocess.run(["pm2", "start", str(pm2_config_path)], 
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                else:
                    result = subprocess.run(["pm2", command, "all"], 
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            else:
                result = subprocess.run(["pm2", command, process], 
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                return f"执行 'pm2 {command} {process}' 时出错:\n{result.stderr}"
            
            # 保存PM2配置
            subprocess.run(["pm2", "save"], check=False)
            
            # 获取更新后的状态
            status_result = subprocess.run(["pm2", "list"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            return f"命令 'pm2 {command} {process}' 执行成功。\n\n当前状态:\n{status_result.stdout}"
        
        except FileNotFoundError:
            return "错误: PM2未安装或未找到。请确保安装了PM2。"
        except Exception as e:
            return f"控制PM2时出错: {str(e)}"

    def pm2_logs(self, process: str = "all", lines: int = 20, project_path: str = None):
        """
        显示PM2管理的ivry服务的日志。
        
        参数:
            process (str, optional): 要查看日志的进程 ('ivry_server', 'cloudflared_tunnel', 或 'all')。
                                    默认为 'all'。
            lines (int, optional): 要显示的日志行数。默认为20。
            project_path (str, optional): 项目目录路径。如果未提供，使用当前工作目录。
        
        返回:
            str: 服务日志
        """
        try:
            # 验证进程
            valid_processes = ["all", "ivry_server", "cloudflared_tunnel"]
            if process not in valid_processes:
                return f"错误: 无效的进程 '{process}'。有效选项: {', '.join(valid_processes)}"
            
            # 确定项目目录
            if project_path:
                project_dir = Path(project_path)
            else:
                project_dir = Path.cwd()
            
            # 日志目录
            logs_dir = project_dir / "logs"
            if not logs_dir.exists():
                return f"错误: 日志目录 '{logs_dir}' 不存在。"
            
            import subprocess
            
            if process == "all":
                # 合并所有日志
                ivry_log = logs_dir / "ivry_server.log"
                cloudflared_log = logs_dir / "cloudflared.log"
                
                ivry_content = ""
                if ivry_log.exists():
                    result = subprocess.run(["tail", "-n", str(lines), str(ivry_log)], 
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    ivry_content = f"=== ivry_server日志 ===\n{result.stdout}\n\n"
                
                cloudflared_content = ""
                if cloudflared_log.exists():
                    result = subprocess.run(["tail", "-n", str(lines), str(cloudflared_log)], 
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    cloudflared_content = f"=== cloudflared_tunnel日志 ===\n{result.stdout}"
                
                return ivry_content + cloudflared_content
            else:
                # 特定进程的日志
                log_file = logs_dir / f"{process}.log"
                if not log_file.exists():
                    return f"错误: 日志文件 '{log_file}' 不存在。"
                
                result = subprocess.run(["tail", "-n", str(lines), str(log_file)], 
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                
                return f"=== {process}日志 (最近{lines}行) ===\n{result.stdout}"
        
        except FileNotFoundError as e:
            return f"错误: 找不到所需的文件或命令: {str(e)}"
        except Exception as e:
            return f"获取日志时出错: {str(e)}"


def main():
    fire.Fire(Cli)
