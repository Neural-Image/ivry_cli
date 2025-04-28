import fire
import os
from pathlib import Path
from pydantic import BaseModel, Field
from business_server import main as start_business_server
from model_server import main as start_model_server_
from cog.server.http import parse_args, main as start_model_server
from communicate import upload_config
from parse_InOut import parse_predict
import requests
import json
import shutil
from util import get_apikey, find_comfyui_processes, get_comfyui_install_path, get_comfyui_ports
import subprocess
import signal
import platform
import time
from heartbeat import HeartbeatManager
from websocket_comfyui import create_predict
from pull_project import generate_predict_file
from find_comfyui_path import find_comfyui_path_by_port
from typing import Optional

#save to current dir
IVRY_CREDENTIAL_DIR = Path.home() / ".ivry"
IVRY_URL = "https://www.ivry.co/"
#IVRY_URL = "https://www.lormul.org/"

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
        """get the status of the heartbeat service"""
        global _heartbeat_manager
        
        if _heartbeat_manager:
            return _heartbeat_manager.get_status()
        return {"running": False, "message": "Heartbeat service not started"}


    def win_path_to_wsl_path(self, win_path: str) -> str:
        """Convert a Windows path to a WSL path"""
        if not win_path:
            return ""
        # Convert backslashes to forward slashes
        path_unix = win_path.replace("\\", "/")
        # Check if the path starts with a drive letter
        if len(path_unix) >= 2 and path_unix[1] == ':':
            drive_letter = path_unix[0].lower()
            path_unix = "/mnt/" + drive_letter + path_unix[2:]
        return path_unix




    def pull_project(self, app_id: str, comfyui_port: str = "8188", project_name: str = None, comfyUI_dir: str = None):
        """
        pull project from server
        
        this function will pull the project from the server and save it to the local directory.
        - app_config.json
        - tunnel_config.json
        - tunnel_credential.json
        - predict.py
        - cog.yaml
        
        Args:
            app_id: the id of the app to pull
            comfyui_port: the port of the comfyUI process
            comfyUI_dir: the dir to your comfyUI process
        
        returns:
            str: A message indicating the result of the operation
        """
        
        import inspect
        import os
        
        current_module_path = os.path.dirname(inspect.getfile(self.__class__))
        current_module_path = os.path.abspath(current_module_path)
        templates_path = os.path.join(current_module_path, "templates")
        
    
        if not os.path.exists(templates_path):
        
            possible_paths = [
                os.path.join(os.getcwd(), "src", "templates"),
                os.path.join(os.path.dirname(os.getcwd()), "src", "templates"),
                os.path.join(os.path.dirname(os.path.dirname(os.getcwd())), "src", "templates")
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    templates_path = path
                    break
        
        cog_yaml_path = os.path.join(templates_path, "cog.yaml")
        if not os.path.exists(cog_yaml_path):
            cog_yaml_content = 'predict: "predict.py:Predictor"\n'
        
        
        apikey = get_apikey()
        headers = {
            'X-API-KEY': str(apikey),
            'Content-Type': 'application/json',
        }
        project_dir = Path("ivry_project/comfyUI_project")
        project_dir.mkdir(parents=True, exist_ok=True)
        try:
            url = f"{IVRY_URL}api/cli/app/{app_id}"
            
            print(f"geting {app_id} 's config...")
            response = requests.get(url, headers=headers)
            response.raise_for_status()  
            
            data = response.json()
            app_type = data["data"]["type"]
            
            if data.get("success") != True:
                return f"error: {data.get('message', 'app created error')}"
            
            
            if app_type == "comfyui":
                app_config = data.get("data", {})
                local_name = "app_" + str(app_id)
                project_path = project_dir / local_name
                dest_path = Path.cwd() / str(project_path)
                if not dest_path.exists():
                    dest_path.mkdir(parents=True, exist_ok=True)
                    print(f"folder {dest_path} created")
                else:
                    print(f"folder {dest_path} already exists")
                
                
            else:
                project_path = Path.cwd()
                
            tunnel_config = data["tunnelCfg"]["config"]
            tunnel_credential = data["tunnelCfg"]["credential"]
            
            tunnel_config_path = project_path / "tunnel_config.json"
            tunnel_credential_path = project_path / "tunnel_credential.json"
            if tunnel_config_path.exists() or tunnel_credential_path.exists():
                override = input(f"Already have an app in this directory, do you want to overwrite? (y/n): ")
                if override.lower() != 'y':
                    return "Operation cancelled by user."
            if tunnel_config:
                with open(tunnel_config_path, "w", encoding="utf-8") as f:
                    json.dump(tunnel_config, f, indent=4, ensure_ascii=False)
                print(f"app_config.json saved to {project_path}")
            
            if tunnel_credential:
                with open(tunnel_credential_path, "w", encoding="utf-8") as f:
                    json.dump(tunnel_credential, f, indent=4, ensure_ascii=False)
                print(f"tunnel_config.json saved to {project_path}")
            if app_type != "comfyui":
                if os.path.exists(cog_yaml_path):
                    shutil.copy(cog_yaml_path, str(project_path) + "/cog.yaml")
                else:
                    with open(str(project_path) + "/cog.yaml", 'w', encoding='utf-8') as f:
                        f.write(cog_yaml_content)
                if app_type == "workflow":
                    with open(str(project_path) + "/cog.yaml", 'w', encoding='utf-8') as f:
                        f.write('predict: "functions.py"\n')
            else:
                
                system_name = platform.uname().release.lower()
                if "microsoft" in system_name:
                    system_name = "windows"
                    if comfyUI_dir == None:
                        return "Please enter your comfyUI dir as parameters, its the dir to your custom_nodes's location. For example: ivry_cli pull_project --app_id 66 --comfyUI_dir E:\ComfyUI_windows_portable\ComfyUI_windows_portable\ComfyUI"
                    win_path = comfyUI_dir
                    wsl_dir = self.win_path_to_wsl_path(win_path)
                    check_path_cmd = f"test -d '{wsl_dir}' && echo 'exists' || echo 'not_exists'"
                    result = subprocess.run(check_path_cmd, shell=True, capture_output=True, text=True)
                    if "not_exists" in result.stdout:
                        return (f"Error: The ComfyUI directory path '{comfyUI_dir}' doesn't exist in WSL after conversion to '{wsl_dir}'.\n"
                                f"Please check the path and make sure it's accessible from WSL.")
                    print(f"ComfyUI directory path '{comfyUI_dir}' validated, converted to WSL path '{wsl_dir}'")



                if comfyUI_dir == None:
                    comfyUI_dir = find_comfyui_path_by_port(int(comfyui_port))
                if not comfyUI_dir:
                    return ("error: cannot find your running comfyUI process " + 
                            f"{comfyui_port} \n" +
                            "if your comfyUI process is running, you could add it to the command。like: ivry_cli pull_project 66 --comfyui_port 8188 --comfyUI_dir /path/to/comfyUI")
                
                generate_predict_file(dir_comfyui=comfyUI_dir,port_comfyui=comfyui_port,input_section=data,os_system=system_name,workflow_name=local_name)
            
    
                source_path = "predict.py"
                destination_path = str(project_path) + "/predict.py"  
                shutil.move(source_path, destination_path)
                if os.path.exists(cog_yaml_path):
                    shutil.copy(cog_yaml_path, str(project_path) + "/cog.yaml")
                else:
                    with open(str(project_path) + "/cog.yaml", 'w', encoding='utf-8') as f:
                        f.write(cog_yaml_content)
                
                
                return f"app {app_id} pulled to {local_name}/ folder"
            
        except requests.exceptions.HTTPError as e:
            return f"HTTP error: {str(e)}"
        except requests.exceptions.ConnectionError:
            return "Connection error: unable to connect to the server. Please check your network connection."
        except requests.exceptions.Timeout:
            return "Timeout error: the request timed out. Please try again later."
        except requests.exceptions.RequestException as e:
            return f"request error: {str(e)}"
        except json.JSONDecodeError:
            return "error: invalid response received from the server (not valid JSON)"
        except Exception as e:
            return f"error: {str(e)}"
        
        
    def parse_predict(self, predict_filename: str = "predict.py"):
        return parse_predict(predict_filename)


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


    def run_server(self, project: str = None, force: bool = False):
        """
        Start the ivry_cli model server and cloudflared tunnel using PM2
        
        This function uses PM2 to manage and monitor the ivry_cli model server and cloudflared tunnel processes.
        Multiple projects can be deployed simultaneously.
        
        Args:
            project (str, optional): Path to the project directory. If not provided,
                                        uses the current working directory.
            force (bool, optional): If True, forcibly restart services even if they're already running.
                                    Default is False.
        
        Returns:
            str: A message indicating the result of the operation
        """
        try:
            import subprocess
            result = subprocess.run(["pm2", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                return "Error: PM2 is not installed or not found. Please ensure PM2 is installed."
        except FileNotFoundError:
            return "Error: PM2 is not installed or not found. Please ensure PM2 is installed."
        if project == "":
            cur_path = str(Path.cwd())
            project = cur_path.split("/")[-1]
        # 确定项目目录
        if project:
            project_dir = Path("ivry_project/comfyUI_project") / Path(project)
            # 提取项目名称，用于服务命名
            project_name = Path(project).name
        else:
            project_dir = Path.cwd()
            # 如果没有指定项目，使用当前目录名称
            project_name = project_dir.name
        
        if not project_dir.exists():
            return f"error: folder '{project_dir}' not found."
        
        tunnel_config_path = project_dir / "tunnel_config.json"
        if not tunnel_config_path.exists():
            return f"error: in '{project_dir}', tunnel_config.json not found."
        
        # 创建日志目录
        logs_dir = project_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        
        # PM2配置文件路径
        pm2_config_path = project_dir / "pm2_config.json"
        
        # 读取 tunnel_config.json
    
        with open(tunnel_config_path, "r") as f:
            tunnel_config = json.load(f)
            model_id = tunnel_config.get("tunnel") or "unknown"

        
        
        # 检查端口占用
        import socket
        def check_port_availability(port, host='127.0.0.1'):
            """检查指定端口是否已被占用"""
            # 寻找可用端口
            if port == 0:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(('', 0))
                port = s.getsockname()[1]
                s.close()
                return port, False
                
            # 检查特定端口
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind((host, port))
                s.close()
                return port, False  # 端口可用
            except socket.error:
                s.close()
                return port, True   # 端口被占用
        
        # 为每个项目分配不同的端口
        base_port = 3009
        # 使用项目名称的哈希值作为端口偏移量
        project_hash = abs(hash(project_name))
        port_offset = project_hash % 100  # 使用哈希值取模作为偏移量
        model_port = base_port + port_offset
        
        # 检查分配的端口，最多尝试10次
        for attempt in range(10):
            model_port, is_used = check_port_availability(model_port)
            if not is_used or force:
                break
            model_port += 1
        
        if is_used and not force:
            return (f"Port {model_port} is already in use, which will prevent ivry_server from starting.\n"
                "Please stop any existing ivry_server instances first or use --force to attempt restart.")
        
        # 使用项目名称创建PM2服务名称
        ivry_server_name = f"ivry_server_{project_name}"
        cloudflared_name = f"ivry_cloudflared_{project_name}"
        
        # 检查这些特定的服务名称是否已经在运行
        result = subprocess.run(["pm2", "list"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if ivry_server_name in result.stdout or cloudflared_name in result.stdout:
            if not force:
                return (f"PM2 already running services for this project.\n"
                    f"check status: ivry_cli pm2_status\n"
                    f"restart: ivry_cli pm2_control restart {ivry_server_name},{cloudflared_name}\n"
                    f"force start: ivry_cli run_server --project {project} --force")
            else:
                # 强制重启，先删除旧服务
                subprocess.run(["pm2", "delete", ivry_server_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                subprocess.run(["pm2", "delete", cloudflared_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # 修改 tunnel_config.json 中的端口
        if "ingress" in tunnel_config:
            #tunnel_config["ingress"]
            tunnel_config["ingress"][0]["service"] = f"http://localhost:{model_port}"
            # 保存修改后的 tunnel_config.json
            with open(tunnel_config_path, "w") as f:
                json.dump(tunnel_config, f, indent=2)
            print(f"Updated tunnel_config.json with new port: {model_port}")
        
        # 配置日志文件路径
        ivry_log_file = (logs_dir / f"{ivry_server_name}.log").resolve()
        cloudflared_log_file = (logs_dir / f"{cloudflared_name}.log").resolve()
        
        # 为每个项目创建独立的PM2_HOME
        pm2_home_dir = project_dir / ".pm2"
        pm2_home_dir.mkdir(exist_ok=True)
        
        # 创建新的PM2配置 - 修改此处，不再使用 --port 参数，而是通过环境变量设置端口
        pm2_config = {
            "apps": [
                {
                    "name": ivry_server_name,
                    "interpreter": "python",
                    "script": shutil.which("ivry_cli"),
                    "args": ["start", "model", f"--upload-url={IVRY_URL}api/cli/upload"],
                    "cwd": str(project_dir),
                    "log_date_format": "YYYY-MM-DD HH:mm:ss Z",
                    "output": str(ivry_log_file),
                    "error": str(ivry_log_file),
                    "merge_logs": True,
                    "autorestart": True,
                    "max_size": "2M",
                    "max_logs": 1,
                    "env": {
                        "PM2_HOME": str(pm2_home_dir),
                        "FORCE_COLOR": "0",
                        "NO_COLOR": "1",
                        "PYTHONIOENCODING": "utf-8",
                        "PYTHONUNBUFFERED": "1",
                        "PORT": str(model_port)  # 设置 PORT 环境变量
                    }
                },
                # cloudflared配置
                {
                    "name": cloudflared_name,
                    "script": "cloudflared",
                    "args": ["tunnel", "--config", "tunnel_config.json", "run"],
                    "cwd": str(project_dir),
                    "log_date_format": "YYYY-MM-DD HH:mm:ss Z",
                    "output": str(cloudflared_log_file),
                    "error": str(cloudflared_log_file),
                    "merge_logs": True,
                    "autorestart": True,
                    "max_size": "2M",
                    "max_logs": 1,
                    "env": {
                        "PM2_HOME": str(pm2_home_dir),
                        "NO_COLOR": "1"
                    }
                }
            ]
        }
        
        # 写入配置文件
        with open(pm2_config_path, "w") as f:
            json.dump(pm2_config, f, indent=4)
        
        # 保存部署信息到项目目录，便于后续管理
        deployment_info = {
            "project_name": project_name,
            "model_id": model_id,
            "ivry_server_name": ivry_server_name,
            "cloudflared_name": cloudflared_name,
            "model_port": model_port,
            "deployed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        with open(project_dir / "deployment_info.json", "w") as f:
            json.dump(deployment_info, f, indent=4)
        
        print(f"Starting ivry_cli model server and cloudflared tunnel for project at: {project_dir}")
        print(f"Model ID: {model_id}")
        print(f"Project name: {project_name}")
        print(f"Using port: {model_port}")
        print(f"Logs will be written to: {logs_dir}")
        
        try:
            # 启动PM2进程
            subprocess.run(["pm2", "start", str(pm2_config_path)], check=True)
            
            # 保存PM2配置
            subprocess.run(["pm2", "save"], check=True)
            
            return (f"Services started with PM2.\n"
                f"Server name: {ivry_server_name}\n"
                f"Tunnel name: {cloudflared_name}\n"
                f"Port: {model_port}\n"
                f"To view status: ivry_cli pm2_status\n"
                f"To control this service: ivry_cli pm2_control [start|stop|restart] {ivry_server_name},{cloudflared_name}\n"
                f"To view logs: ivry_cli pm2_logs {ivry_server_name}\n"
                f"To stop only this service: ivry_cli stop_server --project {project}")
        
        except subprocess.CalledProcessError as e:
            return f"Error when starting PM2: {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"

    def stop_server(self, project: str = None, force: bool = False):
        """
        Stop ivry services managed by PM2 for a specific project or all projects.
        
        Args:
            project (str, optional): Path to the project directory. If not provided,
                                uses the current working directory.
            force (bool, optional): If True, forcibly stop all processes. Default is False.
        
        Returns:
            str: Status information about the stop operation
        """
        try:
            # 确定项目目录
            if project:
                project_dir = Path("ivry_project/comfyUI_project") / Path(project)
                project_name = Path(project).name
            else:
                project_dir = Path.cwd()
                project_name = project_dir.name
            
            # 停止心跳服务
            global _heartbeat_manager
            if _heartbeat_manager:
                _heartbeat_manager.stop()
                _heartbeat_manager = None
                print("Heartbeat service stopped")
            
            # 生成服务名称
            ivry_server_name = f"ivry_server_{project_name}"
            cloudflared_name = f"ivry_cloudflared_{project_name}"
            
            import subprocess
            
            result = subprocess.run(["pm2", "list"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if ivry_server_name not in result.stdout and cloudflared_name not in result.stdout:
                # 尝试从deployment_info.json读取服务名称
                deployment_info_path = project_dir / "deployment_info.json"
                if deployment_info_path.exists():
                    try:
                        with open(deployment_info_path, "r") as f:
                            deployment_info = json.load(f)
                            ivry_server_name = deployment_info.get("ivry_server_name", ivry_server_name)
                            cloudflared_name = deployment_info.get("cloudflared_name", cloudflared_name)
                            
                            # 再次检查这些服务是否在运行
                            if ivry_server_name not in result.stdout and cloudflared_name not in result.stdout:
                                return f"No running ivry services found for project {project_name}."
                    except (json.JSONDecodeError, FileNotFoundError):
                        return f"Error: Could not read deployment info for project at {project_dir}"
                else:
                    return f"No running ivry services found for project {project_name}."
            
            try:
                # 停止ivry_server服务
                subprocess.run(["pm2", "delete", ivry_server_name], check=not force)
                print(f"Stopped {ivry_server_name}")
            except subprocess.CalledProcessError:
                if not force:
                    return f"Failed to stop {ivry_server_name}. Try using the --force flag."
            
            try:
                # 停止cloudflared服务
                subprocess.run(["pm2", "delete", cloudflared_name], check=not force)
                print(f"Stopped {cloudflared_name}")
            except subprocess.CalledProcessError:
                if not force:
                    return f"Failed to stop {cloudflared_name}. Try using the --force flag."
            
            # 保存PM2配置
            subprocess.run(["pm2", "save"], check=False)
            
            return f"Services for project {project_name} have been stopped."
        
        except FileNotFoundError:
            return "Error: PM2 is not installed or not found. Please ensure PM2 is installed."
        except Exception as e:
            if force:
                # 尝试强制停止所有进程
                try:
                    self._force_kill_processes()
                    return "All ivry services have been forcibly terminated."
                except Exception as kill_error:
                    return f"Error: {str(e)}. Force stop error: {str(kill_error)}"
            return f"Error when stopping the server: {str(e)}"
    
    def _legacy_stop_server(self, force: bool = False):
        """旧的停止服务方法，用于向后兼容"""
        import subprocess
        
        result = subprocess.run(["pm2", "list"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # 检查是否有任何ivry服务在运行
        if "ivry_server" not in result.stdout and "ivry_cloudflared" not in result.stdout:
            return "No running ivry services found."
        
        # 查找和停止所有ivry服务
        try:
            # 使用grep命令找出所有ivry相关的PM2服务
            services_result = subprocess.run(
                ["pm2", "list", "--format", "json"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
            
            try:
                services = json.loads(services_result.stdout)
                stopped_services = []
                
                for service in services:
                    name = service.get("name", "")
                    if "ivry_server" in name or "ivry_cloudflared" in name:
                        try:
                            subprocess.run(["pm2", "delete", name], check=not force)
                            stopped_services.append(name)
                        except subprocess.CalledProcessError:
                            if not force:
                                return f"Failed to stop {name}. Try using the --force flag."
                
                if stopped_services:
                    # 保存PM2配置
                    subprocess.run(["pm2", "save"], check=False)
                    return f"Stopped services: {', '.join(stopped_services)}"
                else:
                    return "No ivry services found to stop."
                    
            except json.JSONDecodeError:
                # 如果JSON解析失败，尝试旧方法
                if force:
                    subprocess.run(["pm2", "delete", "all"], check=False)
                    return "All services have been forcibly terminated."
                else:
                    return "Could not identify specific ivry services. Use --force to stop all PM2 services."
        
        except Exception as e:
            if force:
                # 尝试强制停止所有进程
                try:
                    self._force_kill_processes()
                    return "All ivry services have been forcibly terminated."
                except Exception as kill_error:
                    return f"Error: {str(e)}. Force stop error: {str(kill_error)}"
            return f"Error when stopping the server: {str(e)}"

    def _force_kill_processes(self):
  
        import subprocess
        import os
        import signal
        

        def terminate_process(name):
            try:
       
                result = subprocess.run(["pgrep", "-f", name], stdout=subprocess.PIPE, text=True)
                pids = [pid.strip() for pid in result.stdout.strip().split("\n") if pid.strip()]
                
                if pids:
                    for pid in pids:
                        try:
                            os.kill(int(pid), signal.SIGTERM)
                        except ProcessLookupError:
                            continue
                    print(f"stop {name} process with pid: {', '.join(pids)}")
            except Exception as e:
                print(f"stop {name} error: {e}")
        
    
        terminate_process("ivry_cli start model")
        terminate_process("cloudflared tunnel")
        terminate_process("pm2")
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
        kill_process_by_port(3009)
        
    
    def list_deployments(self):
        """
        List all running ivry deployments managed by PM2.
        
        Returns:
            str: Formatted table of running deployments
        """
        try:
            import subprocess
            import json
            from tabulate import tabulate
            
            # 检查PM2是否安装
            result = subprocess.run(["pm2", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                return "Error: PM2 is not installed or not found. Please ensure PM2 is installed."
            
            # 获取所有PM2进程
            services_result = subprocess.run(
                ["pm2", "jlist"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
            
            try:
                services = json.loads(services_result.stdout)
            except json.JSONDecodeError:
                return "Error parsing PM2 process list. Please ensure PM2 is working correctly."
            
            # 筛选出ivry服务
            ivry_services = {}
            for service in services:
                name = service.get("name", "")
                if name.startswith("ivry_server_"):
                    project_id = name.replace("ivry_server_", "")
                    if project_id not in ivry_services:
                        ivry_services[project_id] = {"server": service, "tunnel": None}
                elif name.startswith("ivry_cloudflared_"):
                    project_id = name.replace("ivry_cloudflared_", "")
                    if project_id not in ivry_services:
                        ivry_services[project_id] = {"server": None, "tunnel": service}
                    else:
                        ivry_services[project_id]["tunnel"] = service
            
            if not ivry_services:
                return "No ivry deployments found."
            
            # 准备表格数据
            table_data = []
            headers = ["Project ID", "Server Status", "Tunnel Status", "Port", "Uptime", "Memory"]
            
            for project_id, services in ivry_services.items():
                server = services.get("server")
                tunnel = services.get("tunnel")
                
                server_status = "✓" if server and server.get("pm2_env", {}).get("status") == "online" else "✗"
                tunnel_status = "✓" if tunnel and tunnel.get("pm2_env", {}).get("status") == "online" else "✗"
                
                # 提取端口信息
                port = "N/A"
                if server:
                    env = server.get("pm2_env", {})
                    port = env.get("env", {}).get("PORT", "N/A")
                
                # 计算运行时间
                uptime = "N/A"
                if server:
                    pm2_uptime = server.get("pm2_env", {}).get("pm_uptime", 0)
                    if pm2_uptime:
                        uptime_seconds = (time.time() * 1000 - pm2_uptime) / 1000
                        days = int(uptime_seconds // 86400)
                        hours = int((uptime_seconds % 86400) // 3600)
                        minutes = int((uptime_seconds % 3600) // 60)
                        uptime = f"{days}d {hours}h {minutes}m"
                
                # 内存使用
                memory = "N/A"
                if server:
                    memory_bytes = server.get("monit", {}).get("memory", 0)
                    memory = f"{memory_bytes / (1024 * 1024):.1f} MB"
                
                table_data.append([project_id, server_status, tunnel_status, port, uptime, memory])
            
            # 使用tabulate格式化输出
            return tabulate(table_data, headers=headers, tablefmt="grid")
            
        except Exception as e:
            return f"Error listing deployments: {str(e)}"
    
    
    

    def pm2_status(self, project: str = None):
        """
        Display the status of ivry services managed by PM2.
        
        Args:
            project_path (str, optional): Path to the project directory. If not provided,
                                        uses the current working directory.
        
        Returns:
            str: Status information of PM2-managed processes
        """
        try:
   
            if project:
                project_dir = Path("ivry_project/comfyUI_project") / Path(project)
            else:
                project_dir = Path.cwd()
            
         
            import subprocess
            result = subprocess.run(["pm2", "list"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                return "Error: PM2 is not installed or not found. Please ensure PM2 is installed."
            
  
            return f"PM2 process status :\n\n{result.stdout}"
        
        except FileNotFoundError:
            return "Error: PM2 is not installed or not found. Please ensure PM2 is installed."
        except Exception as e:
            return f"error when get pm2 status: {str(e)}"

    def pm2_control(self, command: str, process: str = "all", project: str = None):
        ### TODO  only control ivry process
        """
        control pm2 process
        
        参数:
            command (str): commands ('start', 'stop', 'restart', 'reload')
            process (str, optional): process ('ivry_server', 'ivry_cloudflared_tunnel', or 'all')。
                                    defalut 'all'。
            project_path (str, optional): Path to the project directory. If not provided,
        
        返回:
            str: Status information of PM2-managed processes
        """
        try:
      
            if command not in ["start", "stop", "restart", "reload"]:
                return f"error: bad command '{command}'.use 'start', 'stop', 'restart' 或 'reload'。"
            
            valid_processes = ["all", "ivry_server", "ivry_cloudflared_tunnel"]
            if process not in valid_processes:
                return f"error: bad process '{process}'. accept process: {', '.join(valid_processes)}"
            
            if project:
                project_dir = Path("ivry_project/comfyUI_project") / Path(project)
            else:
                project_dir = Path.cwd()
            
            import subprocess
            
            if process == "all":
                if command == "start":
                    pm2_config_path = project_dir / "pm2_config.json"
                    if not pm2_config_path.exists():
                        return f"error: please run ivry_cli run_server first."
                    
                    result = subprocess.run(["pm2", "start", str(pm2_config_path)], 
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                else:
                    result = subprocess.run(["pm2", command, "all"], 
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            else:
                result = subprocess.run(["pm2", command, process], 
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                return f"execute 'pm2 {command} {process}' error:\n{result.stderr}"
            
      
            subprocess.run(["pm2", "save"], check=False)
            

            status_result = subprocess.run(["pm2", "list"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            return f"command 'pm2 {command} {process}' sucess \n\n status:\n{status_result.stdout}"
        
        except FileNotFoundError:
            return "Error: PM2 is not installed or not found. Please ensure PM2 is installed."
        except Exception as e:
            return f"error: {str(e)}"

    def pm2_logs(self, process: str = "all", lines: int = 20, project: str = None):
        """
        get pm2 logs
        
        参数:
            process (str, optional): process ('ivry_server', 'ivry_cloudflared_tunnel', or 'all')。
                                    default 'all'。
            lines (int, optional): showing lines of logs。default 20.
            project_path (str, optional): Path to the project directory. If not provided,
        
        返回:
            str: logs
        """
        try:
         
            valid_processes = ["all", "ivry_server", "ivry_cloudflared_tunnel"]
            if process not in valid_processes:
                return f"error: bad process '{process}'. accept process: {', '.join(valid_processes)}"
            
       
            if project:
                project_dir = Path("ivry_project/comfyUI_project") / Path(project)
            else:
                project_dir = Path.cwd()
            
            logs_dir = project_dir / "logs"
            if not logs_dir.exists():
                return f"error: log folder '{logs_dir}' not found."
            
            import subprocess
            
            if process == "all":
       
                ivry_log = logs_dir / "ivry_server.log"
                cloudflared_log = logs_dir / "cloudflared.log"
                
                ivry_content = ""
                if ivry_log.exists():
                    result = subprocess.run(["tail", "-n", str(lines), str(ivry_log)], 
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    ivry_content = f"=== ivry_server log ===\n{result.stdout}\n\n"
                
                cloudflared_content = ""
                if cloudflared_log.exists():
                    result = subprocess.run(["tail", "-n", str(lines), str(cloudflared_log)], 
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    cloudflared_content = f"=== ivry_cloudflared_tunnel log===\n{result.stdout}"
                
                return ivry_content + cloudflared_content
            else:
                log_file = logs_dir / f"{process}.log"
                if not log_file.exists():
                    return f"error: log file '{log_file}' not found."
                
                result = subprocess.run(["tail", "-n", str(lines), str(log_file)], 
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                
                return f"=== {process}log (lateset {lines} lines) ===\n{result.stdout}"
        
        except FileNotFoundError as e:
            return f"error: {str(e)}"
        except Exception as e:
            return f"error when get the logs: {str(e)}"


def main():
    fire.Fire(Cli)
