import json
import subprocess
from pathlib import Path
import time
import os
from typing import Dict, List, Any, Optional, Tuple, Union

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

def generate_predict_file(dir_comfyui: str, port_comfyui: str, input_section: str, os_system: str, workflow_name: str) -> str:
    """生成predict.py文件"""
    print("start to generate predict.py")
    input_list = input_section["data"]["selectedNodes"].keys()
    workflow_name = workflow_name   
    workflow_api_json = input_section["data"]["json"]
    # 获取 selectedNodes
    selected_nodes = input_section["data"]["selectedNodes"]

    # 提取 component_type 和 type，使用 .get() 防止 KeyError
    component_types = {
        node_name: node_data["data"].get("component_type", "N/A")
        for node_name, node_data in selected_nodes.items()
    }

    element_types = {
        node_name: node_data["data"].get("type", "N/A")
        for node_name, node_data in selected_nodes.items()
    }
    print("input_list", input_list)
    print("component_types", component_types) 
    print("element_types", element_types)
    
    input_parameter = ""
    parameter_template = "{parameter_name}: {parameter_type} = Input(description=''),\n                "
    input_parameter_dict = {}
    for index, i in enumerate(component_types):
        cur_type = ""
        if component_types[i] == "input":
            if element_types[i] == "text":
                cur_type = "str"
            elif element_types[i] == "float":
                cur_type = "float"
            else:
                cur_type = "int"
        elif component_types[i] == "textarea":
            cur_type = "str"
        elif component_types[i] == "slider":
            cur_type = "int"
        elif component_types[i] == "checkbox":
            cur_type = "bool"
        elif component_types[i] == "single-select":
            cur_type = "str"
        elif component_types[i] == "file-upload": 
            cur_type = "Path"
        input_parameter_dict[i] = cur_type
        cur_parameter = parameter_template.replace("{parameter_name}", i)
        cur_parameter = cur_parameter.replace("{parameter_type}", cur_type)
        input_parameter += cur_parameter
    print("input_parameter", input_parameter)
   
    
    # if workflow_name == "untitle":
    #     timestamp = time.strftime("%Y%m%d_%H%M%S")
    #     workflow_name = f"workflow_{timestamp}"
    
    
    if not os_system:
        return "Error: Please select your os system"
    
    if not dir_comfyui:
        return "Error: Please enter your comfyUI dir"
    

    wsl_name = "Ubuntu"
    port_str = port_comfyui
    
    if os_system == "windows":
        port_str = get_local_ip(port_comfyui)
        dir_comfyui = win_path_to_wsl_path(dir_comfyui)
        wsl_name = get_wsl_distro_name()
    else:
        port_str = f"127.0.0.1:{port_comfyui}"
    
    # # 确保工作流目录存在
    # os.makedirs("comfyui_workflows", exist_ok=True)
        
    # # 保存工作流
    # with open(f"comfyui_workflows/{workflow_name}", "w") as output_file:
    #     json.dump(state.json_data, output_file, indent=4)
    
    # 读取模板并处理输入部分
    with open("src/templates/predict_comfyui_ui.py", "r") as template_file:
        content = template_file.read()
    
    # 处理逻辑部分
    logic_sections = []
    #print("input_parameter_dict",input_parameter_dict)
    for i, section in enumerate(input_parameter_dict):
        tmp_node_type = input_parameter_dict[section]
        tmp_node_id = section.split("_")[1]
        tmp_node_input = section.split("_")[2]
        if tmp_node_type == 'Path':
            if os_system != "windows":

                logic_sections.append(
                    f"prompt_config['{tmp_node_id}']['inputs']['{tmp_node_input}'] = "
                    f"str({section})\n        "
                )
            else:
                wsl_path = r"\\wsl$\\" + wsl_name + r"\tmp"

                logic_sections.append(
                    f"prompt_config['{tmp_node_id}']['inputs']['{tmp_node_input}'] = r'{wsl_path}'"
                    f" + '/' + str({section})\n        "
                )
        else:

            logic_sections.append(
                f"prompt_config['{tmp_node_id}']['inputs']['{tmp_node_input}'] = "
                f"{section}\n        "
            )
        
    
    logic_section = "".join(logic_sections)
    print("finish to generate predict.py")
    # 获取工作流文件的绝对路径
    workflow_path = Path(f"comfyui_workflows/{workflow_name}.json").resolve()
    with workflow_path.open("w", encoding="utf-8") as f:
        json.dump(workflow_api_json, f, ensure_ascii=False, indent=4)
    # 替换模板中的占位符
    content = content.replace("{{dir_comfyui}}", f"'{dir_comfyui}'")
    content = content.replace("{{port_comfyui}}", f"'{port_str}'")
    content = content.replace("{{input_section}}", input_parameter)
    content = content.replace("{{workflow_dir}}", f"r'{workflow_path}'")
    content = content.replace("{{logic_section}}", logic_section)
    # 保存为 predict.py
    print("finish to generate predict.py")
    with open("predict.py", "w") as predict_file:
        predict_file.write(content)
        
   

    