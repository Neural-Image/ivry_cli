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


    def pull_project(self, app_id: str, comfyui_port: str = "8188", project_name: str = None):
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
            
            if data.get("status") != "success":
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
            
            comfyUI_dir = find_comfyui_path_by_port(int(comfyui_port))
            # 根据配置数据创建必要的预测器文件
            system_name = platform.system().lower()
            print("1")
            generate_predict_file(dir_comfyui=comfyUI_dir,port_comfyui=comfyui_port,input_section=data,os_system=system_name,workflow_name=local_name)
            print("2")
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


    def run_server(self, project_path: str = None, detached: bool = False, force: bool = False):
        """
        Starts both the ivry_cli model server and cloudflared tunnel in a single command
        with supervisor process monitoring.
        
        This function combines the functionalities of starting the ivry_cli model server
        and the cloudflared tunnel, using supervisor to monitor and manage the processes.
        
        Args:
            project_path (str, optional): Path to the project directory. If not provided,
                                        uses the current working directory.
            detached (bool, optional): If True, runs the servers in detached mode (background).
                                    Default is False.
            force (bool, optional): If True, forcibly restart services even if they're already running.
                                Default is False.
        
        Returns:
            str: A message indicating the result of the operation
        """
        

        if not SUPERVISOR_AVAILABLE:
            return "Error: The supervisor package is not installed. Please install it with: pip install supervisor"
        
 
        try:
            # Try to import supervisor
            import supervisor.supervisord as supervisord
            from supervisor.options import ServerOptions
            from supervisor.xmlrpc import SupervisorTransport
            import xmlrpc.client
            import socket
        except ImportError:
            return "Error: The supervisor package is not installed. Please install it with: pip install supervisor"
        
        # Determine project directory
        if project_path:
            project_dir = Path(project_path)
        else:
            project_dir = Path.cwd()
        
        # Verify project directory exists and contains required files
        if not project_dir.exists():
            return f"Error: Project directory '{project_dir}' does not exist."
        
        tunnel_config = project_dir / "tunnel_config.json"
        if not tunnel_config.exists():
            return f"Error: Could not find tunnel_config.json in '{project_dir}'. Make sure this is a valid ivry project directory."
        
        # Create supervisor directory if it doesn't exist
        supervisor_dir = project_dir / "supervisor"
        supervisor_dir.mkdir(exist_ok=True)
        
        # Create logs directory if it doesn't exist
        logs_dir = project_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        
        # Define supervisor files
        supervisor_conf = supervisor_dir / "supervisord.conf"
        supervisor_log_file = (logs_dir / "supervisord.log").resolve()
        supervisor_pid_file = (supervisor_dir / "supervisord.pid").resolve()
        supervisor_sock_file = (supervisor_dir / "supervisor.sock").resolve()
        
        # Check for already running supervisor instance
        if supervisor_pid_file.exists() and not force:
            try:
                # Read PID file
                with open(supervisor_pid_file, "r") as f:
                    pid = int(f.read().strip())
                    
                # Check if process exists
                try:
                    os.kill(pid, 0)  # Signal 0 only checks if process exists, doesn't terminate it
                    # Process exists, try to connect to the XMLRPC interface
                    try:
                        transport = xmlrpc.client.ServerProxy(
                            "http://127.0.0.1",
                            transport=SupervisorTransport(None, None, str(supervisor_sock_file))
                        )
                        # Get process info to verify connection works
                        process_info = transport.supervisor.getAllProcessInfo()
                        
                        return (f"A supervisor instance is already running (PID: {pid}).\n"
                            f"To check status: ivry_cli supervisor_status\n"
                            f"To restart: ivry_cli supervisor_control restart\n"
                            f"To force start a new instance: ivry_cli run_server --force")
                    except Exception:
                        # Can't connect to XMLRPC, supervisor might be in bad state
                        print(f"Supervisor process is running but XMLRPC interface is not responding.")
                        if force:
                            print("Force flag is set, terminating existing process...")
                            try:
                                os.kill(pid, 15)  # SIGTERM
                                import time
                                time.sleep(2)  # Give it time to terminate
                            except OSError:
                                pass
                        else:
                            return (f"Supervisor process (PID: {pid}) appears to be in a bad state.\n"
                                f"Use --force to terminate it and start a new instance.")
                except OSError:
                    # Process doesn't exist, clean up PID file
                    supervisor_pid_file.unlink()
                    print(f"Removed stale PID file from previous instance")
            except (ValueError, IOError) as e:
                # Invalid PID file format or can't read it
                supervisor_pid_file.unlink()
                print(f"Removed invalid PID file: {e}")
        
        # Check if the sock file exists and remove if needed
        if supervisor_sock_file.exists():
            try:
                supervisor_sock_file.unlink()
                print(f"Removed stale socket file from previous instance")
            except OSError as e:
                print(f"Warning: Could not remove stale socket file: {e}")
        
        # Check if ivry server port is already in use
        def check_port(port):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind(('127.0.0.1', port))
                s.close()
                return False  # Port is free
            except socket.error:
                return True  # Port is in use
        
        # ivry server typically uses port 3009
        if check_port(3009):
            print("Warning: Port 3009 is already in use. This may cause conflicts with the ivry server.")
            if not force:
                return ("Port 3009 is already in use, which will prevent ivry_server from starting.\n"
                    "Please stop any existing ivry_server instances first or use --force to attempt restart.")
        
        try:
            # Get model_id from tunnel config if possible
            try:
                with open(tunnel_config, "r") as f:
                    config = json.load(f)
                    model_id = config.get("tunnel") or "unknown"
            except (json.JSONDecodeError, FileNotFoundError):
                model_id = "unknown"
            
            # Absolute paths for log files
            ivry_log_file = (logs_dir / "ivry_server.log").resolve()
            cloudflared_log_file = (logs_dir / "cloudflared.log").resolve()
            
            # Create supervisor configuration
            supervisor_config = f"""[unix_http_server]
                                    file={supervisor_sock_file}
                                    chmod=0700

                                    [supervisord]
                                    logfile={supervisor_log_file}
                                    pidfile={supervisor_pid_file}
                                    childlogdir={logs_dir}
                                    directory={project_dir}

                                    [rpcinterface:supervisor]
                                    supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

                                    [supervisorctl]
                                    serverurl=unix://{supervisor_sock_file}

                                    [program:ivry_server]
                                    command=ivry_cli start model --upload-url={IVRY_URL}pc/client-api/upload
                                    directory={project_dir}
                                    autostart=true
                                    autorestart=true
                                    redirect_stderr=true
                                    stdout_logfile={ivry_log_file}
                                    stderr_logfile={ivry_log_file}
                                    stopasgroup=true
                                    killasgroup=true
                                    priority=1

                                    [program:cloudflared_tunnel]
                                    command=cloudflared tunnel --config tunnel_config.json run
                                    directory={project_dir}
                                    autostart=true
                                    autorestart=true
                                    redirect_stderr=true
                                    stdout_logfile={cloudflared_log_file}
                                    stderr_logfile={cloudflared_log_file}
                                    stopasgroup=true
                                    killasgroup=true
                                    priority=2

                                    [group:ivry_services]
                                    programs=ivry_server,cloudflared_tunnel
                                    """

            # Write supervisor configuration
            with open(supervisor_conf, "w") as f:
                f.write(supervisor_config)
            
            print(f"Starting ivry_cli model server and cloudflared tunnel for project at: {project_dir}")
            print(f"Model ID: {model_id}")
            print(f"Logs will be written to: {logs_dir}")
            
            # Start supervisor
            options = ServerOptions()
            options.configfile = str(supervisor_conf)
            
            if detached:
                # Start supervisor in daemon mode
                options.daemon = True
                supervisord.main(args=["-c", str(supervisor_conf)])
                
                # Start heartbeat service if model_id is available
                if model_id and model_id != "unknown":
                    try:
                        global _heartbeat_manager
                        apikey = get_apikey()
                        upload_url = f"{IVRY_URL}pc/client-api/heartbeat"
                        
                        # Stop any existing heartbeat manager
                        if _heartbeat_manager:
                            _heartbeat_manager.stop()
                        
                        # Start new heartbeat manager
                        _heartbeat_manager = HeartbeatManager(
                            upload_url=upload_url,
                            model_id=model_id,
                            api_key=apikey,
                            interval=3600  # 1 hour interval by default
                        )
                        _heartbeat_manager.start()
                        print("Heartbeat service started")
                    except Exception as e:
                        print(f"Warning: Failed to start heartbeat service: {e}")
                
                return (f"Services started in detached mode with supervisor.\n"
                    f"Supervisor PID file: {supervisor_pid_file}\n"
                    f"To check status: ivry_cli supervisor_status\n"
                    f"To control services: ivry_cli supervisor_control [start|stop|restart]\n"
                    f"To view logs, check: {logs_dir}")
            else:
                # Start supervisor in foreground mode
                print("Starting services in foreground mode with supervisor...")
                print("Press Ctrl+C to stop all services")
                
                # Start supervisord
                supervisord.main(args=["-n", "-c", str(supervisor_conf)])
                
                return "Services have been stopped."
        
        except Exception as e:
            return f"Error starting services with supervisor: {str(e)}"

    def stop_server(self, project_path: str = None):
        """
        Stops all supervised ivry services.
        
        Args:
            project_path (str, optional): Path to the project directory. If not provided,
                                        uses the current working directory.
        
        Returns:
            str: Status information about the stop operation
        """
        try:
            import xmlrpc.client
            from supervisor.xmlrpc import SupervisorTransport
        except ImportError:
            return "Error: The supervisor package is not installed. Please install it with: pip install supervisor"
        
        # Determine project directory
        if project_path:
            project_dir = Path(project_path)
        else:
            project_dir = Path.cwd()
        
        supervisor_dir = project_dir / "supervisor"
        supervisor_conf = supervisor_dir / "supervisord.conf"
        supervisor_sock_file = supervisor_dir / "supervisor.sock"
        supervisor_pid_file = supervisor_dir / "supervisord.pid"
        
        if not supervisor_conf.exists():
            return f"Error: Supervisor configuration not found at {supervisor_conf}. No services to stop."
        
        if not supervisor_sock_file.exists() or not supervisor_pid_file.exists():
            return f"Error: Supervisor does not appear to be running. No active services found."
        
        try:
            # Read PID file
            try:
                with open(supervisor_pid_file, "r") as f:
                    pid = int(f.read().strip())
            except (ValueError, IOError):
                return "Error: Unable to read supervisor PID file. It might be corrupted."
            
            # Check if process exists
            try:
                os.kill(pid, 0)
            except OSError:
                return "No active supervisor process found. Cleaning up stale files."
            
            # Connect to supervisor via Unix socket
            try:
                transport = xmlrpc.client.ServerProxy(
                    "http://127.0.0.1",
                    transport=SupervisorTransport(None, None, str(supervisor_sock_file))
                )
                
                # First get process info for reporting
                process_info = transport.supervisor.getAllProcessInfo()
                running_processes = [p['name'] for p in process_info if p['state'] == 20]  # 20 = RUNNING
                
                # Stop all processes
                transport.supervisor.stopAllProcesses()
                
                # Shutdown supervisor itself
                transport.supervisor.shutdown()
                
                # Give it a moment to shutdown
                import time
                time.sleep(2)
                
                # Check if supervisor is still running
                try:
                    os.kill(pid, 0)
                    print(f"Supervisor process (PID: {pid}) is still running. Sending SIGTERM...")
                    os.kill(pid, 15)  # SIGTERM
                    time.sleep(1)
                except OSError:
                    # Process is gone, which is what we want
                    pass
                
                # Clean up files if they still exist
                if supervisor_sock_file.exists():
                    supervisor_sock_file.unlink()
                if supervisor_pid_file.exists():
                    supervisor_pid_file.unlink()
                
                # Heartbeat manager stop
                global _heartbeat_manager
                if _heartbeat_manager:
                    _heartbeat_manager.stop()
                    _heartbeat_manager = None
                    print("Heartbeat service stopped")
                
                if running_processes:
                    return f"Successfully stopped services: {', '.join(running_processes)}"
                else:
                    return "Successfully stopped supervisor. No services were running."
                
            except Exception as e:
                # If we can't stop cleanly via XMLRPC, try to kill the process
                try:
                    os.kill(pid, 15)  # SIGTERM
                    time.sleep(2)
                    
                    # Check if it's still running
                    try:
                        os.kill(pid, 0)
                        os.kill(pid, 9)  # SIGKILL as last resort
                        return f"Forcibly terminated supervisor process (PID: {pid})"
                    except OSError:
                        return f"Terminated supervisor process (PID: {pid})"
                except OSError:
                    return f"Failed to terminate supervisor process: {str(e)}"
        
        except Exception as e:
            return f"Error stopping services: {str(e)}"

    def supervisor_status(self, project_path: str = None):
        """
        Displays the status of supervised ivry services.
        
        Args:
            project_path (str, optional): Path to the project directory. If not provided,
                                        uses the current working directory.
        
        Returns:
            str: Status information of supervised processes
        """
        try:
            import xmlrpc.client
            from supervisor.xmlrpc import SupervisorTransport
        except ImportError:
            return "Error: The supervisor package is not installed. Please install it with: pip install supervisor"
        
        # Determine project directory
        if project_path:
            project_dir = Path(project_path)
        else:
            project_dir = Path.cwd()
        
        supervisor_dir = project_dir / "supervisor"
        supervisor_conf = supervisor_dir / "supervisord.conf"
        supervisor_sock_file = supervisor_dir / "supervisor.sock"
        supervisor_pid_file = supervisor_dir / "supervisord.pid"
        
        if not supervisor_conf.exists():
            return f"Error: Supervisor configuration not found at {supervisor_conf}"
        
        if not supervisor_sock_file.exists() or not supervisor_pid_file.exists():
            return f"Error: Supervisor does not appear to be running. No active services found."
        
        # Read PID file
        try:
            with open(supervisor_pid_file, "r") as f:
                pid = int(f.read().strip())
        except (ValueError, IOError):
            return "Error: Unable to read supervisor PID file. It might be corrupted."
        
        # Check if process exists
        try:
            os.kill(pid, 0)
        except OSError:
            return "No active supervisor process found. Cleaning up stale files."
        
        try:
            # Connect to supervisor via Unix socket
            transport = xmlrpc.client.ServerProxy(
                "http://127.0.0.1",
                transport=SupervisorTransport(None, None, str(supervisor_sock_file))
            )
            
            # Get process info
            process_info = transport.supervisor.getAllProcessInfo()
            
            # Check if supervisor is actually running
            if not process_info:
                return "Supervisor is running but no processes are defined."
            
            # Format and return status information
            status_info = f"{'PROCESS NAME':<20} {'STATUS':<10} {'PID':<8} {'UPTIME'}\n"
            status_info += "-" * 60 + "\n"
            
            for process in process_info:
                name = process['name']
                state = process['statename']
                pid = process['pid'] or "N/A"
                uptime = "-"
                if process.get('start'):
                    from datetime import datetime
                    start_time = datetime.fromtimestamp(process['start'])
                    uptime = str(datetime.now() - start_time).split('.')[0]  # Remove microseconds
                
                status_info += f"{name:<20} {state:<10} {pid:<8} {uptime}\n"
            
            # Add supervisor process itself
            status_info += "-" * 60 + "\n"
            status_info += f"{'supervisord':<20} {'RUNNING':<10} {pid:<8} N/A\n"
            
            return status_info
        
        except Exception as e:
            return f"Error getting supervisor status: {str(e)}"

    def supervisor_control(self, command: str, process: str = "all", project_path: str = None):
        """
        Controls supervised ivry services.
        
        Args:
            command (str): Control command ('start', 'stop', 'restart')
            process (str, optional): Process to control ('ivry_server', 'cloudflared_tunnel', or 'all').
                                    Default is 'all'.
            project_path (str, optional): Path to the project directory. If not provided,
                                        uses the current working directory.
        
        Returns:
            str: Result of the control operation
        """
        try:
            import xmlrpc.client
            from supervisor.xmlrpc import SupervisorTransport
        except ImportError:
            return "Error: The supervisor package is not installed. Please install it with: pip install supervisor"
        
        # Validate command
        if command not in ["start", "stop", "restart"]:
            return f"Error: Invalid command '{command}'. Use 'start', 'stop', or 'restart'."
        
        # Validate process
        valid_processes = ["all", "ivry_server", "cloudflared_tunnel", "ivry_services"]
        if process not in valid_processes:
            return f"Error: Invalid process '{process}'. Valid options are: {', '.join(valid_processes)}"
        
        # Determine project directory
        if project_path:
            project_dir = Path(project_path)
        else:
            project_dir = Path.cwd()
        
        supervisor_dir = project_dir / "supervisor"
        supervisor_conf = supervisor_dir / "supervisord.conf"
        supervisor_sock_file = supervisor_dir / "supervisor.sock"
        supervisor_pid_file = supervisor_dir / "supervisord.pid"
        
        if not supervisor_conf.exists():
            return f"Error: Supervisor configuration not found at {supervisor_conf}"
        
        if not supervisor_sock_file.exists() or not supervisor_pid_file.exists():
            return f"Error: Supervisor does not appear to be running. Start it first with 'ivry_cli run_server'."
        
        try:
            # Read PID file
            try:
                with open(supervisor_pid_file, "r") as f:
                    pid = int(f.read().strip())
            except (ValueError, IOError):
                return "Error: Unable to read supervisor PID file. It might be corrupted."
            
            # Check if process exists
            try:
                os.kill(pid, 0)
            except OSError:
                return "No active supervisor process found. Start it first with 'ivry_cli run_server'."
            
            # Connect to supervisor via Unix socket
            transport = xmlrpc.client.ServerProxy(
                "http://127.0.0.1",
                transport=SupervisorTransport(None, None, str(supervisor_sock_file))
            )
            
            # Execute the command
            result = ""
            if process == "all":
                if command == "start":
                    transport.supervisor.startAllProcesses()
                    result = "All processes started"
                elif command == "stop":
                    transport.supervisor.stopAllProcesses()
                    result = "All processes stopped"
                elif command == "restart":
                    transport.supervisor.stopAllProcesses()
                    time.sleep(1)  # Brief pause to ensure processes have time to stop
                    transport.supervisor.startAllProcesses()
                    result = "All processes restarted"
            elif process == "ivry_services":
                group_name = "ivry_services"
                if command == "start":
                    transport.supervisor.startProcessGroup(group_name)
                    result = f"Process group '{group_name}' started"
                elif command == "stop":
                    transport.supervisor.stopProcessGroup(group_name)
                    result = f"Process group '{group_name}' stopped"
                elif command == "restart":
                    transport.supervisor.stopProcessGroup(group_name)
                    time.sleep(1)  # Brief pause to ensure processes have time to stop
                    transport.supervisor.startProcessGroup(group_name)
                    result = f"Process group '{group_name}' restarted"
            else:
                if command == "start":
                    transport.supervisor.startProcess(process)
                    result = f"Process '{process}' started"
                elif command == "stop":
                    transport.supervisor.stopProcess(process)
                    result = f"Process '{process}' stopped"
                elif command == "restart":
                    transport.supervisor.stopProcess(process)
                    time.sleep(1)  # Brief pause to ensure process has time to stop
                    transport.supervisor.startProcess(process)
                    result = f"Process '{process}' restarted"
            
            # Get updated status
            process_info = transport.supervisor.getAllProcessInfo()
            status_info = f"\nCurrent Status:\n"
            status_info += f"{'PROCESS NAME':<20} {'STATUS':<10} {'PID':<8}\n"
            status_info += "-" * 45 + "\n"
            
            for p in process_info:
                name = p['name']
                state = p['statename']
                pid = p['pid'] or "N/A"
                status_info += f"{name:<20} {state:<10} {pid:<8}\n"
            
            return f"{result}\n{status_info}"
        
        except Exception as e:
            return f"Error controlling supervisor: {str(e)}"



def main():
    fire.Fire(Cli)
