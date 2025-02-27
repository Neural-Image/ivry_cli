import gradio as gr
import subprocess
import ast
import json
import copy
import os
import signal
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
from parse_InOut import parse_predict_return

# 全局变量
class State:
    def __init__(self):
        self.json_data = {}
        self.json_name = ""
        self.final_selection = []
        self.inputs_counter = {"int": 0, "float": 0, "str": 0, "Path": 0, "bool": 0}
        self.workflow_parsing = ""
        self.final_inputs = []
        self.input_dict = {}
        self.input_type = {}
        self.workflow_json = ""
        self.python_dict_inputs = {}
        self.signature = ''
        self.input_names = []
        self.signature_list = []
        self.project_x_process = None
        self.cloudflare_process = None

# 全局状态实例
state = State()

# 常量
LOG_FILE = "client.log"
MAX_LOG_SIZE = 5 * 1024 * 1024  # 5MB
IVRY_URL = "https://www.ivry.co/"
COMPONENT_TEMPLATES = {
    "slider": '''{{
            "component_type": "slider",
            "title": "{element_name}",
            "description": "",
            "defaultvalue":"" ,
            "min":0 ,
            "max":10
        }},
        ''',
    "input": '''{{
            "component_type": "input",
            "title": "{element_name}",
            "description": "",
            "defaultvalue": "hello world",
            "placeholder": "type prompt here"
        }},
        ''',
    "multi-select": '''{{
            "component_type": "multi-select",
            "title": "{element_name}",
            "description": "",
            "defaultvalue": [],
            "options": [
            {{ name: "Startup", ram: "12GB", cpus: "6 CPUs", disk: "256GB SSD disk" }},
            {{ name: "Business", ram: "16GB", cpus: "8 CPUs", disk: "512GB SSD disk" }},
            ]
        }},
        ''',
    "checkbox": '''{{
            "component_type": "checkbox",
            "title": "{element_name}",
            "description": "",
            "defaultvalue": "true"
        }},
        ''',
    "single-select": '''{{
            "component_type": "single-select",
            "title": "{element_name}",
            "description": "",
            "defaultvalue": "",
            "options": [
                "Tom Cook",
                "Wade Cooper",
                "Tanya Fox",
                "Arlene Mccoy",
                "Devon Webb"
                ]
        }},
        ''',
    "textarea": '''{{
            "component_type": "textarea",
            "title": "{element_name}",
            "description": "",
            "placeholder": "type what you want here",
            "defaultvalue": ""
        }},
        ''',
    "file-upload": '''{{
            "component_type": "file-upload",
            "title": "{element_name}",
            "description": ""
        }},
        '''
}

def validate_signature_data(signature_data: List[Dict[str, Any]]) -> Optional[str]:
    """验证签名数据的有效性"""
    for item in signature_data:
        component_type = item.get("component_type")
        if component_type == "slider":
            if "min" not in item or "max" not in item:
                return f"Error: Missing range for slider '{item.get('title')}'"
            if not isinstance(item["min"], (int, float)) or not isinstance(item["max"], (int, float)):
                return f"Error: Slider '{item.get('title')}' must have numeric min and max values"
            if item["min"] >= item["max"]:
                return f"Error: Slider '{item.get('title')}' min must be less than max"
        elif component_type == "input":
            if "defaultvalue" not in item:
                return f"Error: Missing defaultvalue for input '{item.get('title')}'"
        elif component_type == "checkbox":
            if "defaultvalue" not in item or not isinstance(item["defaultvalue"], bool):
                return f"Error: Checkbox '{item.get('title')}' must have a boolean defaultvalue"
        elif component_type == "file-upload":
            if "description" not in item:
                return f"Error: Missing description for file-upload '{item.get('title')}'"
    return None


def generate_signature_file(project_name: str, signature_text: str) -> str:
    """生成签名文件"""
    if not project_name:
        return "Error: Please enter your project name"
    
    if not os.path.isdir(project_name):
        return "Error: Please init your project first"
    
    prefix = "[\n"
    suffix = "\n]"
    
    # 移除尾部的逗号
    signature_text = signature_text.rstrip()
    if signature_text.endswith(","):
        signature_text = signature_text[:-1]
    
    # 格式化最终的JSON
    signature_text = prefix + signature_text + suffix
    
    try:
        signature_json_data = json.loads(signature_text)
        validation_error = validate_signature_data(signature_json_data)
        if validation_error:
            return validation_error
        
        output_path = os.path.join(project_name, 'predict_signature.json')
        with open(output_path, 'w') as file:
            json.dump(signature_json_data, file, indent=4, ensure_ascii=False)
        
        return f"{output_path} generated successfully!"
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON format - {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


def get_wsl_distro_name() -> str:
    """获取WSL发行版名称"""
    try:
        result = subprocess.run(
            ["bash", "-c", "echo $WSL_DISTRO_NAME"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, subprocess.TimeoutExpired):
        return "Ubuntu"  # Default to Ubuntu if failed


def win_path_to_wsl_path(win_path: str) -> str:
    """将Windows路径转换为WSL路径"""
    if not win_path:
        return ""
    
    # 统一将反斜杠替换为正斜杠
    path_unix = win_path.replace("\\", "/")
    
    # 如果路径形如 "C:/..."，那么把它转为 "/mnt/c/..."
    if len(path_unix) >= 2 and path_unix[1] == ':':
        drive_letter = path_unix[0].lower()
        path_unix = "/mnt/" + drive_letter + path_unix[2:]
    
    return path_unix


def get_local_ip(port: Union[str, int]) -> str:
    """获取本地IP地址和端口"""
    try:
        result = subprocess.check_output(
            "ip route | grep default | awk '{print $3}'", 
            shell=True, 
            text=True,
            timeout=5
        ).strip()
        return f"{result}:{port}"
    except (subprocess.SubprocessError, subprocess.TimeoutExpired):
        return f"127.0.0.1:{port}"


def generate_predict_file(dir_comfyui: str, port_comfyui: str, input_section: str, os_system: str) -> str:
    """生成predict.py文件"""
    if not os_system:
        return "Error: Please select your os system"
    
    if not dir_comfyui:
        return "Error: Please enter your comfyUI dir"
    
    try:
        wsl_name = "Ubuntu"
        port_str = port_comfyui
        
        if os_system == "windows":
            port_str = get_local_ip(port_comfyui)
            dir_comfyui = win_path_to_wsl_path(dir_comfyui)
            wsl_name = get_wsl_distro_name()
        else:
            port_str = f"127.0.0.1:{port_comfyui}"
        
        # 确保工作流目录存在
        os.makedirs("comfyui_workflows", exist_ok=True)
        
        if not state.json_data:
            return "Error: Please upload correct API JSON"
            
        # 保存工作流
        with open(f"comfyui_workflows/{state.json_name}", "w") as output_file:
            json.dump(state.json_data, output_file, indent=4)
        
        # 读取模板并处理输入部分
        with open("src/templates/predict_comfyui_ui.py", "r") as template_file:
            content = template_file.read()
        
        # 处理输入部分
        input_sections = [s for s in input_section.split(',') if s.strip()]
        processed_sections = []
        
        for i, section in enumerate(input_sections):
            if "\n" in section:
                section = section.split("\n")[1]
            
            if "Input(description='" not in section:
                continue
                
            if not state.input_names[i]:
                processed_sections.append(f'ivry_{section},\n                ')
            else:
                tmp = section.replace(section.split(':')[0], state.input_names[i], 1)
                processed_sections.append(f'{tmp},\n                ')
        
        input_parameter = "".join(processed_sections)
        
        # 处理逻辑部分
        logic_sections = []
        cur_input_dict = copy.deepcopy(state.input_dict)
        cur_input_type = copy.deepcopy(state.input_type)
        
        for i, section in enumerate(input_sections):
            if "\n" in section:
                section = section.split("\n")[1]
                
            if "Input(description='" not in section:
                continue
                
            tmp_node_id = section.split('_')[0]
            
            if tmp_node_id not in cur_input_dict or tmp_node_id not in cur_input_type:
                continue
                
            tmp_node_type = cur_input_type[tmp_node_id][0]
            tmp_node_input = cur_input_dict[tmp_node_id][0]
            
            # 根据不同OS和类型处理路径
            if tmp_node_type == 'Path':
                if os_system != "windows":
                    if not state.input_names[i]:
                        logic_sections.append(
                            f"prompt_config['{tmp_node_id}']['inputs']['{tmp_node_input}'] = "
                            f"str(ivry_{tmp_node_id}_{tmp_node_input})\n        "
                        )
                    else:
                        logic_sections.append(
                            f"prompt_config['{tmp_node_id}']['inputs']['{tmp_node_input}'] = "
                            f"str({state.input_names[i]})\n        "
                        )
                else:
                    wsl_path = r"\\wsl$\\" + wsl_name + r"\tmp"
                    if not state.input_names[i]:
                        logic_sections.append(
                            f"prompt_config['{tmp_node_id}']['inputs']['{tmp_node_input}'] = r'{wsl_path}'"
                            f" + '/' + str(ivry_{tmp_node_id}_{tmp_node_input})[5:]\n        "
                        )
                    else:
                        logic_sections.append(
                            f"prompt_config['{tmp_node_id}']['inputs']['{tmp_node_input}'] = r'{wsl_path}'"
                            f" + '/' + str({state.input_names[i]})[5:]\n        "
                        )
            else:
                if not state.input_names[i]:
                    logic_sections.append(
                        f"prompt_config['{tmp_node_id}']['inputs']['{tmp_node_input}'] = "
                        f"ivry_{tmp_node_id}_{tmp_node_input}\n        "
                    )
                else:
                    logic_sections.append(
                        f"prompt_config['{tmp_node_id}']['inputs']['{tmp_node_input}'] = "
                        f"{state.input_names[i]}\n        "
                    )
            
            # 处理完一个输入后，移除它以处理下一个
            if len(cur_input_dict[tmp_node_id]) > 1:
                cur_input_dict[tmp_node_id].pop(0)
                cur_input_type[tmp_node_id].pop(0)
        
        logic_section = "".join(logic_sections)
        
        # 获取工作流文件的绝对路径
        workflow_path = Path(f"comfyui_workflows/{state.json_name}").resolve()
        
        # 替换模板中的占位符
        content = content.replace("{{dir_comfyui}}", f"'{dir_comfyui}'")
        content = content.replace("{{port_comfyui}}", f"'{port_str}'")
        content = content.replace("{{input_section}}", input_parameter)
        content = content.replace("{{workflow_dir}}", f"r'{workflow_path}'")
        content = content.replace("{{logic_section}}", logic_section)
        
        # 保存为 predict.py
        with open("predict.py", "w") as predict_file:
            predict_file.write(content)
            
        return "predict.py generated successfully!"
    except Exception as e:
        return f"Error generating predict.py: {str(e)}"


def process_selection(main_selection: str, sub_selection: str, sub_sub_selection: str, rename: str) -> str:
    """处理用户选择并更新工作流解析结果"""
    if not rename:
        rename = sub_selection
        
    # 验证重命名
    if " " in rename:
        return "Please use underscore instead of space"
        
    if rename in state.input_names:
        return "This name is already taken. Please give another name."
        
    if any(char in "!@#$%^&*-+=<>?/.,;:'\"[]{}\\|`~" for char in rename):
        return "Please use letters or numbers."
        
    if not rename[0].isalpha():
        return "First letter must be alphabeta"
    
    node_id = main_selection.split(' ')[0]
    full_id = node_id + sub_selection
    
    if full_id not in state.final_inputs:
        # 添加到输入字典
        if node_id not in state.input_dict:
            state.input_dict[node_id] = [sub_selection]
        else:
            state.input_dict[node_id].append(sub_selection)
        
        # 添加到类型字典
        if node_id not in state.input_type:
            state.input_type[node_id] = [sub_sub_selection]
        else:
            state.input_type[node_id].append(sub_sub_selection)
        
        # 添加重命名
        state.input_names.append(rename)
        state.final_inputs.append(full_id)
        
        # 格式化显示
        entry = f"{node_id}_{sub_selection}: {sub_sub_selection}= Input(description=''),-------->{rename}<--------"
        if state.workflow_parsing:
            state.workflow_parsing += f"\n{entry}"
        else:
            state.workflow_parsing = entry
    else:
        return "This key pairs already in predict.py, if you want to change it, please delete it with delete button first"
    
    return state.workflow_parsing


def upload_json(file) -> Union[Dict, str]:
    """上传并解析JSON文件"""
    if file is None:
        return "No file uploaded!"
        
    try:
        with open(file.name, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return "Invalid JSON file!"
    except Exception as e:
        return f"Error loading file: {str(e)}"


def extract_keys(data: Dict) -> List[str]:
    """从JSON数据中提取键"""
    keys = []
    if isinstance(data, dict):
        for key, value in data.items():
            if "inputs" in data[key]:
                if "_meta" in data[key] and "title" in data[key]["_meta"]:
                    keys.append(f"{key} - {data[key]['_meta']['title']}")
                else:
                    keys.append(key)
    return keys


def upload_json_and_update_menu(file) -> gr.update:
    """上传JSON文件并更新菜单选项"""
    if file is None:
        return gr.update(choices=[], value=None)
    
    try:
        with open(file.name, "r") as f:
            state.json_data = json.load(f)
        
        state.json_name = os.path.basename(file.name)
        keys = extract_keys(state.json_data)
        
        if not keys:
            return gr.update(choices=[], value=None)
            
        return gr.update(choices=keys, value=keys[0])
    except Exception:
        return gr.update(choices=[], value=None)


def extract_input_keys(data: Dict, key: str) -> List[str]:
    """提取指定键的输入键"""
    if key in data and "inputs" in data[key]:
        return list(data[key]["inputs"].keys())
    return []


def update_submenu(main_key: str) -> gr.update:
    """根据主菜单选择更新子菜单"""
    node_id = main_key.split(' ')[0]
    if node_id in state.json_data:
        input_keys = extract_input_keys(state.json_data, node_id)
        return gr.update(choices=input_keys, value=input_keys[0] if input_keys else None)
    return gr.update(choices=[], value=None)


def update_subsubmenu(outputs: str) -> gr.update:
    """更新子子菜单"""
    try:
        outputs_list = ast.literal_eval(outputs)
        return gr.update(choices=outputs_list, value=outputs_list[0] if outputs_list else None)
    except (SyntaxError, ValueError):
        return gr.update(choices=[], value=None)


def clear_cache():
    """清除所有全局状态"""
    state.__init__()  # 重置所有状态
    return None


def delete_last_line(text: str) -> str:
    """删除文本的最后一行"""
    if not text.strip():
        return text
    
    workflow_lines = state.workflow_parsing.split("\n")
    
    if workflow_lines:
        last_line = workflow_lines[-1]
        node_id = last_line.split('_')[0]
        
        if node_id in state.input_dict:
            full_id = node_id + state.input_dict[node_id][-1]
            
            if full_id in state.final_inputs:
                state.final_inputs.remove(full_id)
                
                if len(state.input_dict[node_id]) < 2:
                    del state.input_dict[node_id]
                else:
                    state.input_dict[node_id].pop()
                
                if node_id in state.input_type and len(state.input_type[node_id]) < 2:
                    del state.input_type[node_id]
                elif node_id in state.input_type:
                    state.input_type[node_id].pop()
                
                if state.input_names:
                    state.input_names.pop()
        
        workflow_lines.pop()
        state.workflow_parsing = "\n".join(workflow_lines)
        
        lines = text.split("\n")
        if lines:
            lines.pop()
        return "\n".join(lines)
        
    return text


def run_command(command: str, timeout: int = 30) -> str:
    """运行命令并返回结果"""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            text=True, 
            capture_output=True,
            timeout=timeout
        )
        
        if result.returncode == 0:
            return f"Command executed successfully:\n{result.stdout}"
        else:
            return f"Command failed with error:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout} seconds"
    except Exception as e:
        return f"Error executing command: {str(e)}"


def run_login(api_key: str) -> str:
    """登录到ivry"""
    if not api_key:
        return "Error: API key is required"
        
    return run_command(f"ivry_cli login {api_key}")


def run_init(project_name: str) -> str:
    """初始化项目"""
    if not project_name:
        return "Error: Project name is required"
        
    return run_command(f"ivry_cli init_app --project_name {project_name} --mode comfyui")


def run_upload(project_name: str) -> str:
    """上传项目"""
    if not project_name:
        return "Error: Please enter your project name"
    
    project_dir = Path(project_name)
    if not project_dir.exists():
        return "Error: Please init your project first"
    
    source_file = Path("predict.py")
    if not source_file.exists():
        return "Error: predict.py does not exist."
    
    try:
        # 复制predict.py到项目目录
        import shutil
        destination_file = project_dir / source_file.name
        shutil.copy(source_file, destination_file)
        
        # 上传应用
        return run_command(f"ivry_cli upload_app --model_name {project_name}")
    except Exception as e:
        return f"Error: {str(e)}"


def start_project_x(target_path: str) -> str:
    """启动ivry_cli服务器"""
    if not target_path:
        return "Error: Please enter your project name"
    
    target_dir = Path(target_path)
    if not target_dir.exists():
        return f"Error: Target path '{target_path}' does not exist."
    
    try:
        # 启动ivry_cli
        with open(target_dir / "client.log", "w") as log_file:
            subprocess.Popen(
                [
                    "ivry_cli", "start", "model",
                    f"--upload-url={IVRY_URL}pc/client-api/upload"
                ],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=target_dir
            )
        
        # 启动cloudflare隧道
        with open(target_dir / "cloudflare.log", "w") as log_file:
            subprocess.Popen(
                ["cloudflared", "tunnel", "--config", "tunnel_config.json", "run"],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=target_dir
            )
            
        return f"Service started in {target_path}. Logs are being written to client.log and cloudflare.log."
    except Exception as e:
        return f"Error starting service: {str(e)}"


def stop_processes() -> str:
    """停止所有服务进程"""
    try:
        def terminate_process(name: str) -> None:
            try:
                result = subprocess.run(["pgrep", "-f", name], stdout=subprocess.PIPE, text=True)
                pids = [pid.strip() for pid in result.stdout.strip().split("\n") if pid.strip()]
                
                for pid in pids:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        print(f"Terminated {name} process with PID: {pid}")
                    except ProcessLookupError:
                        continue
            except Exception as e:
                print(f"Error stopping {name}: {e}")
        
        def kill_process_by_port(port: int) -> None:
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
        
        # 终止ivry_cli进程
        terminate_process("ivry_cli")
        
        # 终止cloudflared进程
        terminate_process("cloudflared tunnel --config tunnel_config.json run")
        
        # 终止3009端口上的进程
        kill_process_by_port(3009)
        
        return "All server processes have been stopped."
    except Exception as e:
        return f"Error stopping processes: {str(e)}"


def upload_python_signature(file) -> gr.update:
    """上传Python文件并提取签名"""
    if file is None:
        return gr.update(choices=[], value=None)
    
    try:
        from pathlib import Path
        json_data = parse_predict_return(Path(file.name), "json")
        state.python_dict_inputs = {item["name"]: item["type"] for item in json_data["inputs"]}
        
        if not state.python_dict_inputs:
            return gr.update(choices=[], value=None)
            
        unique_keys = list(state.python_dict_inputs.keys())
        return gr.update(choices=unique_keys, value=unique_keys[0])
    except Exception:
        return gr.update(choices=[], value=None)


def upload_python(file):
    """上传Python文件并解析"""
    if file is None:
        return "No file uploaded!"
    
    try:
        from pathlib import Path
        json_data = parse_predict_return(Path(file.name), "json")
        state.python_dict_inputs = {item["name"]: item["type"] for item in json_data["inputs"]}
        return state.python_dict_inputs
    except Exception as e:
        return f"Error: {str(e)}"


def update_component_type(element_name: str) -> gr.update:
    """根据元素类型更新组件类型选项"""
    if element_name not in state.python_dict_inputs:
        return gr.update(choices=[], value=None)
    
    element_type = state.python_dict_inputs[element_name]
    component_types = {
        "int": ["slider", "input", "multi-select", "single-select"],
        "float": ["slider", "input", "multi-select", "single-select"],
        "str": ["textarea", "input", "multi-select", "single-select"],
        "bool": ["checkbox"],
        "Path": ["file-upload", "single-select"]
    }
    
    if element_type in component_types and component_types[element_type]:
        choices = component_types[element_type]
        return gr.update(choices=choices, value=choices[0])
    
    return gr.update(choices=[], value=None)


def process_signature_selection(element_name: str, component_type: str) -> str:
    """处理签名选择并更新签名文本"""
    if not element_name or not component_type:
        return "Error: Element name and component type are required"
    
    if element_name in state.signature_list:
        return "This input already in the json, please select another one"
    
    state.signature_list.append(element_name)
    
    if component_type in COMPONENT_TEMPLATES:
        state.signature += COMPONENT_TEMPLATES[component_type].format(element_name=element_name)
    else:
        return f"Unsupported component type: {component_type}"
    
    return state.signature


def delete_last_part(text: str) -> str:
    """从签名中删除最后一部分"""
    state.signature = text
    
    parts = state.signature.strip().split("},")
    
    if len(parts) > 0:
        state.signature = "},".join(parts[:-1]) + "}"
        if state.signature == "}":
            state.signature = ""
        if state.signature_list:
            state.signature_list.pop()
    
    return state.signature


def refresh_logs(project_name: str) -> str:
    """刷新日志显示"""
    if not project_name:
        return "Error: Project name is required"
    
    log_path = os.path.join(project_name, "client.log")
    
    try:
        with open(log_path, "r") as log_file:
            return log_file.read()
    except FileNotFoundError:
        return "No logs available yet."
    except Exception as e:
        return f"Error reading logs: {e}"


def sync_data(data: str) -> str:
    """同步数据，保持不变"""
    return data


def refresh_component(value) -> gr.update:
    """重新渲染组件，不更改值"""
    return gr.update()


def main():
    """主函数：创建和启动Gradio UI"""
    print("Starting Gradio UI...")
    css_path = os.path.abspath("src/styles.css")
    
    with gr.Blocks(css_paths=css_path) as demo:
        with gr.Tabs():
            # 初始化选项卡
            with gr.Tab("ivry init"):
                gr.Markdown("# Init Ivry")
                gr.Markdown("## Step 1: Login to ivry! Create your account and enter your apikey.")
                
                with gr.Accordion("click to see ivry website", open=False): 
                    gr.HTML("""
                        <iframe 
                            src="https://www.ivry.co/account" 
                            width="100%" 
                            height="500" 
                            frameborder="0">
                        </iframe>
                    """)
                
                gr.Markdown("### enter your apikey to login to ivry")
                api_key_input = gr.Textbox(label="API Key", placeholder="enter your API Key", type="password")
                output_text = gr.Textbox(label="login result")
                login_button = gr.Button("api login")
                login_button.click(run_login, inputs=api_key_input, outputs=output_text)

                gr.Markdown("## Step 2: init your app! Please give it a good name!")
                project_name_input = gr.Textbox(label="Project Name", placeholder="enter your project name")
                init_output_text = gr.Textbox(label="init result")
                init_button = gr.Button("init")
                init_button.click(run_init, inputs=project_name_input, outputs=init_output_text)

                gr.Markdown("## Step 3: Go to Predict.py Generator tab to generate your predict.py!")

            # Predict.py 生成器选项卡
            with gr.Tab("Predict.py Generator"):
                options_list = ["int", "float", "str", "Path", "bool"]

                gr.Markdown("## Cog predict.py Generator")
                os_system = gr.Dropdown(label="os system", choices=["linux/macos", "windows"],value="linux/macos" ,interactive=True)
                
                with gr.Row():
                    with gr.Column():
                        dir_comfyui = gr.Textbox(
                            label="comfy dir", 
                            placeholder="comfy dir, (where your main.py locate) example: /home/ivry/comfyui", 
                            value=""
                        )
                    with gr.Column():    
                        port_comfyui = gr.Textbox(label="comfyUI port", placeholder="port_comfyui", value="8188")
                
                gr.Markdown("### Upload a JSON File")
                with gr.Row():
                    file_input = gr.File(label="Upload JSON File", file_types=[".json"])
                    json_output = gr.JSON(label="File Content (Loaded in Memory)")
                
                file_input.change(upload_json, inputs=file_input, outputs=json_output)
                
                gr.Markdown("### Choose your inputs")
                with gr.Row():
                    main_menu = gr.Dropdown(label="Node Id and name", choices=[], interactive=True)
                    
                    with gr.Column(scale=1, min_width=300, elem_id="dropdown-container"):
                        sub_menu = gr.Dropdown(label="input options", choices=[], interactive=True)
                        refresh_btn = gr.Button("↻", elem_id="tiny-refresh-btn")
                    
                    sub_sub_menu = gr.Dropdown(
                        label="Input types", 
                        choices=options_list, 
                        interactive=True, 
                        value="int"
                    )
                    
                    rename = gr.Textbox(label="Optional: give the input a name", interactive=True)
                
                refresh_btn.click(refresh_component, inputs=[sub_menu], outputs=sub_menu)
                main_menu.change(update_submenu, inputs=main_menu, outputs=sub_menu)
                
                submit_button = gr.Button("Submit")
                output_workflow = gr.Textbox(label="Result", interactive=False)
                
                submit_button.click(
                    process_selection, 
                    inputs=[main_menu, sub_menu, sub_sub_menu, rename], 
                    outputs=output_workflow
                )
                
                delete_button = gr.Button("Delete Last Line")
                delete_button.click(delete_last_line, inputs=output_workflow, outputs=output_workflow)
                
                file_input.change(upload_json_and_update_menu, inputs=file_input, outputs=main_menu)
                file_input.change(clear_cache, inputs=[], outputs=output_workflow)
                
                final_output = gr.Textbox(label="Output", interactive=False)
                generate_button = gr.Button("Generate predict.py")
                generate_button.click(
                    generate_predict_file,
                    inputs=[dir_comfyui, port_comfyui, output_workflow, os_system],
                    outputs=final_output
                )

            # 编辑输入选项卡
            with gr.Tab("Edit Inputs"):
                gr.Markdown("# Edit your UI")
                gr.Markdown("## Upload your predict.py (If you just used predict.py generator, predict.py locate in your ivry root folder)")
                
                python_input = gr.File(label="Upload predict.py File", file_types=[".py"])
                python_output = gr.JSON(label="File Content (Loaded in Memory)")
                python_input.change(upload_python, inputs=python_input, outputs=python_output)
                
                with gr.Row():
                    element_name = gr.Dropdown(label="element name", choices=[], interactive=True)
                    component_type = gr.Dropdown(label="component type", choices=[], interactive=True)
                
                with gr.Row():
                    submit_button = gr.Button("Submit")
                    delete_button = gr.Button("Delete Last component")
                
                predict_signature_output = gr.Textbox(
                    label="Result", 
                    interactive=True,
                    max_lines=30
                )
                
                submit_button.click(
                    process_signature_selection, 
                    inputs=[element_name, component_type], 
                    outputs=predict_signature_output
                )
                
                delete_button.click(
                    delete_last_part, 
                    inputs=predict_signature_output, 
                    outputs=predict_signature_output
                )
                
                element_name.change(update_component_type, inputs=element_name, outputs=component_type)
                python_input.change(upload_python_signature, inputs=python_input, outputs=element_name)
                python_input.change(clear_cache, inputs=[], outputs=output_workflow)
                
                signature_final_output = gr.Textbox(label="signature Output", interactive=False)
                
                with gr.Row():
                    preoject_siginature_name = gr.Textbox(
                        label="signature Project Name", 
                        placeholder="enter your project name"
                    )
                    signature_generate_button = gr.Button("Generate predict_signature.json")
                
                signature_generate_button.click(
                    generate_signature_file,
                    inputs=[preoject_siginature_name, predict_signature_output],
                    outputs=signature_final_output
                )

            # 上传和托管应用选项卡
            with gr.Tab("upload and host app"):
                gr.Markdown("## Step 4: upload your app, enter your project name")
                
                upload_name_input = gr.Textbox(
                    label="Upload Project Name", 
                    placeholder="enter your project name"
                )
                
                upload_output_text = gr.Textbox(label="upload result")
                upload_button = gr.Button("upload")
                upload_button.click(run_upload, inputs=upload_name_input, outputs=upload_output_text)
                
                gr.Markdown("### Subprocess Runner")
                project_x_path_input = gr.Textbox(label="Target Path for ivry_cli")
                
                with gr.Row():
                    gr.Markdown("#### ivry_cli")
                    start_project_x_button = gr.Button("Start ivry_cli")
                    project_x_status = gr.Textbox(label="ivry_cli Status", interactive=False)
                
                with gr.Row():
                    gr.Markdown("#### Stop Processes")
                    stop_processes_button = gr.Button("Stop All Processes")
                    stop_processes_status = gr.Textbox(label="Stop Processes Status", interactive=False)
                
                log_output = gr.Textbox(label="Logs", lines=20, interactive=False)
                refresh_button = gr.Button("Refresh Logs")
                refresh_button.click(refresh_logs, inputs=project_x_path_input, outputs=log_output)
                
                # 跨选项卡字段同步
                project_name_input.change(fn=sync_data, inputs=project_name_input, outputs=upload_name_input)
                project_name_input.change(fn=sync_data, inputs=project_name_input, outputs=project_x_path_input)
                project_name_input.change(fn=sync_data, inputs=project_name_input, outputs=preoject_siginature_name)
                upload_name_input.change(fn=sync_data, inputs=upload_name_input, outputs=project_x_path_input)
                
                # 按钮交互逻辑
                start_project_x_button.click(start_project_x, inputs=project_x_path_input, outputs=project_x_status)
                stop_processes_button.click(stop_processes, outputs=stop_processes_status)

    # 启动Gradio应用
    demo.launch()


if __name__ == "__main__":
    main()