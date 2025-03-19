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
        
        apikey = get_apikey()
        headers = {
            'X-Dev-Token': str(apikey),
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
            
            if data.get("success") != True:
                return f"error: {data.get('message', 'app created error')}"
            
            app_config = data.get("data", {})
            local_name = "app_" + str(app_id)
            project_path = project_dir / local_name
            dest_path = Path.cwd() / str(project_path)
            if not dest_path.exists():
                dest_path.mkdir(parents=True, exist_ok=True)
                print(f"folder {dest_path} created")
            else:
                print(f"folder {dest_path} already exists")
            
            tunnel_config = data["tunnelCfg"]["config"]
            tunnel_credential = data["tunnelCfg"]["credential"]
            
            
            if tunnel_config:
                with open(project_path / "tunnel_config.json", "w", encoding="utf-8") as f:
                    json.dump(tunnel_config, f, indent=4, ensure_ascii=False)
                print(f"app_config.json saved to {dest_path}")
            
            if tunnel_credential:
                with open(project_path / "tunnel_credential.json", "w", encoding="utf-8") as f:
                    json.dump(tunnel_credential, f, indent=4, ensure_ascii=False)
                print(f"tunnel_config.json saved to {dest_path}")
            if data["data"]["type"] == "python":
                pass
            else:
                
                system_name = platform.uname().release.lower()
                if "microsoft" in system_name:
                    system_name = "windows"
                    if comfyUI_dir == None:
                        return "Please enter your comfyUI dir as parameters, its the dir to your custom_nodes's location. For example: ivry_cli pull_project --app_id 66 --comfyUI_dir E:\ComfyUI_windows_portable\ComfyUI_windows_portable\ComfyUI"
                    
        


                if comfyUI_dir == None:
                    comfyUI_dir = find_comfyui_path_by_port(int(comfyui_port))
                if not comfyUI_dir:
                    return ("error: cannot find your running comfyUI process " + 
                            f"{comfyui_port} 上。\n" +
                            "if your comfyUI process is running, you could add it to the command。like: ivry_cli pull_project 66 --comfyui_port 8188 --comfyUI_dir /path/to/comfyUI")
                
                generate_predict_file(dir_comfyui=comfyUI_dir,port_comfyui=comfyui_port,input_section=data,os_system=system_name,workflow_name=local_name)
            
    
            source_path = "predict.py"
            destination_path = str(project_path) + "/predict.py"  
            shutil.move(source_path, destination_path)
            shutil.copy("src/templates/cog.yaml", str(project_path) + "/cog.yaml")
            
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
                'X-Dev-Token': str(apikey),
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
        
        This function uses PM2 to manage and monitor the ivry_cli model server and cloudflared tunnel processes
        
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
        

        if project:
            project_dir = Path("ivry_project/comfyUI_project") / Path(project)
        else:
            project_dir = Path.cwd()
        
        if not project_dir.exists():
            return f"error: folder '{project_dir}' not found."
        
        tunnel_config = project_dir / "tunnel_config.json"
        if not tunnel_config.exists():
            return f"error: in '{project_dir}', tunnel_config.json not found."
        

        logs_dir = project_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        

        pm2_config_path = project_dir / "pm2_config.json"
        

        try:
            with open(tunnel_config, "r") as f:
                config = json.load(f)
                model_id = config.get("tunnel") or config.get("token") or "unknown"
        except (json.JSONDecodeError, FileNotFoundError):
            model_id = "unknown"
        

        import socket
        def check_port(port):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind(('127.0.0.1', port))
                s.close()
                return False  
            except socket.error:
                return True  

        if check_port(3009) and not force:
            return ("Port 3009 is already in use, which will prevent ivry_server from starting.\n"
                "Please stop any existing ivry_server instances first or use --force to attempt restart.")
        

        result = subprocess.run(["pm2", "list"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if "ivry_server" in result.stdout or "ivry_cloudflared_tunnel" in result.stdout:
            if not force:
                return ("PM2 already running \n"
                    "check status:ivry_cli pm2_status\n"
                    "restart: ivry_cli pm2_control restart\n"
                    "force start: ivry_cli run_server --force")
            else:
                subprocess.run(["pm2", "delete", "ivry_server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                subprocess.run(["pm2", "delete", "ivry_cloudflared_tunnel"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        

        ivry_log_file = (logs_dir / "ivry_server.log").resolve()
        cloudflared_log_file = (logs_dir / "cloudflared.log").resolve()

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
                    "max_size": "2M",
                    "max_logs": 1,  # 限制为只保留1个日志文件
                    "env": {
                        "PM2_HOME": str(project_dir / ".pm2"),
                        "FORCE_COLOR": "0",   
                        "NO_COLOR": "1",      
                        "PYTHONIOENCODING": "utf-8",   
                        "PYTHONUNBUFFERED": "1"       
                    }
                },
                # cloudflared configuration
                {
                    "name": "ivry_cloudflared_tunnel",
                    "script": "cloudflared",
                    "args": ["tunnel", "--config", "tunnel_config.json", "run"], 
                    "cwd": str(project_dir),
                    "log_date_format": "YYYY-MM-DD HH:mm:ss Z",
                    "output": str(cloudflared_log_file),
                    "error": str(cloudflared_log_file),
                    "merge_logs": True,
                    "autorestart": True,
                    "max_size": "2M",
                    "max_logs": 1,  # 限制为只保留1个日志文件
                    "env": {
                        "PM2_HOME": str(project_dir / ".pm2"),
                        "NO_COLOR": "1"  
                    }
                }
            ]
        }
        
        # 写入配置文件
        with open(pm2_config_path, "w") as f:
            json.dump(pm2_config, f, indent=4)
        
        print(f"Starting ivry_cli model server and cloudflared tunnel for project at: {project_dir}")
        print(f"Model ID: {model_id}")
        print(f"Logs will be written to: {logs_dir}")
        print(f"Log files will be limited to 1MB each")
        
        try:
            # 启动PM2进程
            subprocess.run(["pm2", "start", str(pm2_config_path)], check=True)
            
            # 保存PM2配置
            subprocess.run(["pm2", "save"], check=True)
            
            return (f"Services started with PM2.\n"
                f"To view status: ivry_cli pm2_status\n"
                f"To control services: ivry_cli pm2_control [start|stop|restart]\n"
                f"To view logs: ivry_cli pm2_logs\n"
                f"To stop all services: ivry_cli stop_server")
        
        except subprocess.CalledProcessError as e:
            return f"error when start pm2: {str(e)}"
        except Exception as e:
            return f"error: {str(e)}"

    def stop_server(self, project: str = None, force: bool = False):
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
      
            if project:
                project_dir = Path("ivry_project/comfyUI_project") / Path(project)
            else:
                project_dir = Path.cwd()
            
         
            global _heartbeat_manager
            if _heartbeat_manager:
                _heartbeat_manager.stop()
                _heartbeat_manager = None
                print("Heartbeat service stopped")
            
    
            import subprocess
            
            result = subprocess.run(["pm2", "list"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if "ivry_server" not in result.stdout and "ivry_cloudflared_tunnel" not in result.stdout:
                return "No running ivry services found."
            
            try:
      
                subprocess.run(["pm2", "delete", "ivry_server"], check=not force)
            except subprocess.CalledProcessError:
                if not force:
                    return "Failed to stop ivry_server. Try using the --force flag."
            
            try:
   
                subprocess.run(["pm2", "delete", "ivry_cloudflared_tunnel"], check=not force)
            except subprocess.CalledProcessError:
                if not force:
                    return "Failed to stop ivry_cloudflared_tunnel. Try using the --force flag."
            
           
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
            return "Error: PM2 is not installed or not found. Please ensure PM2 is installed."
        except Exception as e:
            if force:
      
                try:
                    self._force_kill_processes()
                    return "All ivry services have been forcibly terminated."
                except Exception as kill_error:
                    return f"error: {str(e)}. force stop error: {str(kill_error)}"
            return f"error when stop the server: {str(e)}"

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
