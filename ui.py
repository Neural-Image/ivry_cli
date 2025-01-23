import gradio as gr
import subprocess
import ast
import json
import copy
import socket

json_data = {}
final_selection = []
inputs_counter = {
    "int":0, 
    "float":0, 
    "str":0, 
    "Path":0 ,
    "bool":0
}
workflow_parsing = ""
final_inputs = []
input_dict = {}
input_type = {}

def generate_predict_file(dir_comfyui, port_comfyui, input_section):
    if dir_comfyui == '':
        raise ValueError("Please enter your comfyUI dir")
 

    cur_input_dict = copy.deepcopy(input_dict)


    if not dir_comfyui:
        return "Error: Please enter your comfyUI dir!"
    # 读取模板文件内容
    input_parameter = ""
    with open("src/templates/predict_comfyui_ui.py", "r") as template_file:
        content = template_file.read()
    # print(input_section)
    input_section = input_section.split(',')
    for index, i in enumerate(input_section):
        if "\n" in i:
            input_section[index] = i.replace("\n", "")
        if i == '':
            input_section.pop(index)

    # ### Inputs 


    for i in input_section:
        #input_dict[]
        input_parameter = input_parameter + 'ivry_' + i + ",\n                "  

    
    ###

    ### workflow json

    logic_section = ""
    for index, i in enumerate(input_section):
        tmp_node_id = i.split('_')[0]
        tmp_node_input = cur_input_dict[tmp_node_id][-1]
        if tmp_node_input == 'Path':
            logic_section += f"prompt_config['{tmp_node_id}']['inputs']['{tmp_node_input}'] = str(ivry_{tmp_node_id}_{tmp_node_input})" +  "\n        "
        else:
            logic_section += f"prompt_config['{tmp_node_id}']['inputs']['{tmp_node_input}'] = ivry_{tmp_node_id}_{tmp_node_input}" +  "\n        "

        if len(cur_input_dict[tmp_node_id]) > 1:
            cur_input_dict[tmp_node_id].pop()






    ###
    
    
    
    
    
    
    
    
    
    # 替换模板中的占位符
    content = content.replace("{{dir_comfyui}}", f"'{dir_comfyui}'")
    content = content.replace("{{port_comfyui}}", f"'{port_comfyui}'")
    content = content.replace("{{input_section}}", input_parameter)
    content = content.replace("{{logic_section}}", logic_section)





    # 保存为 predict.py
    with open("gradio_predict.py", "w") as predict_file:
        predict_file.write(content)

    return "predict.py generated successfully!"

def update_selection(selection):
    global inputs_counter
    final_selection.append(selection + "_" + str(inputs_counter[selection]))
    inputs_counter[selection] += 1
    return final_selection  # 返回更新后的列表

def delete_selection(option_to_delete):
    global inputs_counter
    if (option_to_delete + "_" + str(inputs_counter[option_to_delete] - 1)) in final_selection:
        final_selection.remove(option_to_delete + "_" + str(inputs_counter[option_to_delete] - 1))
        inputs_counter[option_to_delete] -= 1
    return final_selection  # 返回更新后的列表



# 处理最终选择后的输出
def process_selection(main_selection, sub_selection, sub_sub_selection):
    global workflow_parsing
    global final_inputs
    global input_dict
    global input_type
    if (main_selection.split(' ')[0] + sub_selection) not in final_inputs:
        if main_selection.split(' ')[0] not in input_dict:
            input_dict[main_selection.split(' ')[0]] = [sub_selection]
        else:
            input_dict[main_selection.split(' ')[0]].append(sub_selection)
        
        if main_selection.split(' ')[0] not in input_type:
            input_type[main_selection.split(' ')[0]] = [sub_sub_selection]
        else:
            input_type[main_selection.split(' ')[0]].append(sub_sub_selection)
        
        
        final_inputs.append(main_selection.split(' ')[0] + sub_selection)
        if len(final_inputs) == 1:
            workflow_parsing += main_selection.split(' ')[0] + '_' + sub_selection + ": " + sub_sub_selection + "= Input(description=''),"
        else:
            workflow_parsing += "\n" + main_selection.split(' ')[0] + '_' + sub_selection + ": " + sub_sub_selection + "= Input(description=''),"

    return workflow_parsing

# 处理上传的 JSON 文件并将其保存到内存
def upload_json(file):
    if file is not None:
        # 读取 JSON 文件
        with open(file.name, "r") as f:
            json_data = json.load(f)
        # 返回文件内容作为内存中的数据
        return json_data  # 可以将数据存入全局变量或返回显示在界面上
    return "No file uploaded!"

# 递归提取 JSON 中所有键，返回列表
def extract_keys(data):
    keys = []
    if isinstance(data, dict):  # 如果是字典
        for key, value in data.items():
            if "inputs" in data[key]:
                if "_meta" in data[key]:
                    if "title" in data[key]["_meta"]:
                        keys.append(key + " - " + data[key]["_meta"]["title"])
                else:
                     keys.append(key)

    return keys

# 上传 JSON 文件并更新主菜单
def upload_json_and_update_menu(file):
    global json_data
    if file is not None:
        with open(file.name, "r") as f:
            json_data = json.load(f)
        keys = extract_keys(json_data)  # 提取所有键
        unique_keys = list(set(keys))  # 去重
        return gr.update(choices=unique_keys, value=unique_keys[0])  # 更新 Dropdown 的选项
    return gr.update(choices=[], value=None)

# 提取 JSON 中所有 keys 的函数（针对 inputs）
def extract_input_keys(data, key):
    # 检查是否存在指定的 key，并且有 "inputs"
    if key in data and "inputs" in data[key]:
        return list(data[key]["inputs"].keys())  # 返回 inputs 中的所有键
    return []

# 根据主菜单选择更新次级菜单
def update_submenu(main_key):
    if main_key.split(' ')[0] in json_data:
        input_keys = extract_input_keys(json_data, main_key.split(' ')[0])
        return gr.update(choices=input_keys, value=input_keys[0] if input_keys else None)
    return gr.update(choices=[], value=None)


# 根据主菜单选择更新次级菜单
def update_subsubmenu(outputs):
    outputs = ast.literal_eval(outputs)
    return gr.update(choices=outputs, value=outputs[0] if outputs else None)


# 定义清理逻辑
def clear_cache():
    global json_data
    global final_selection
    global inputs_counter
    global workflow_parsing
    global final_inputs
    global input_dict
    global input_type
    
    json_data = {}
    final_selection = []
    inputs_counter = {
        "int":0, 
        "float":0, 
        "str":0, 
        "Path":0 ,
        "bool":0
    }
    workflow_parsing = ""
    final_inputs = []
    input_dict = {}
    input_type = {}
    return None  # 返回默认值以清空组件


# 定义函数，删除文本框中的最后一行
def delete_last_line(text):
    global workflow_parsing
    global final_inputs
    global input_dict
    global input_type

    
    if text.strip():  # 检查文本框是否为空
        workflow_lines = workflow_parsing.split("\n")
        if workflow_lines[-1].split('_')[0] + input_dict[workflow_lines[-1].split('_')[0]][-1] in final_inputs:
            final_inputs.remove(workflow_lines[-1].split('_')[0]+ input_dict[workflow_lines[-1].split('_')[0]][-1])

            if len(input_dict[workflow_lines[-1].split('_')[0]]) < 2:
                del input_dict[workflow_lines[-1].split('_')[0]]
            else:
                input_dict[workflow_lines[-1].split('_')[0]].pop()
            
            if len(input_type[workflow_lines[-1].split('_')[0]]) < 2:
                del input_type[workflow_lines[-1].split('_')[0]]
            else:
                input_type[workflow_lines[-1].split('_')[0]].pop()
        print('input_dict',input_dict)
        print('input_type',input_type)
        workflow_lines.pop()
        
        workflow_parsing = "\n".join(workflow_lines)
        lines = text.split("\n")
        lines.pop()  # 删除最后一行
        return "\n".join(lines)
    return text  # 如果文本框为空，保持原样


def run_login(api_key):
    try:
        # 构造命令
        command = f"project-x login {api_key}"
        
        # 运行命令
        result = subprocess.run(command, shell=True, text=True, capture_output=True)
        
        # 根据执行结果返回
        if result.returncode == 0:
            return f"成功登录！输出：\n{result.stdout}"
        else:
            return f"登录失败！错误：\n{result.stderr}"
    except Exception as e:
        return f"执行命令出错：{str(e)}"
    
def run_init(project_name):
    try:
        # 构造命令
        command = f"project-x init_app --project_name {project_name} --mode comfyui"
        
        # 运行命令
        result = subprocess.run(command, shell=True, text=True, capture_output=True)
        
        # 根据执行结果返回
        if result.returncode == 0:
            return f"成功初始化！输出：\n{result.stdout}"
        else:
            return f"初始化失败！错误：\n{result.stderr}"
    except Exception as e:
        return f"执行命令出错：{str(e)}"

def run_upload(project_name):
    try:
        # 构造命令
        command = f"project-x upload_app --model_name {project_name}"
        
        # 运行命令
        result = subprocess.run(command, shell=True, text=True, capture_output=True)
        
        # 根据执行结果返回
        if result.returncode == 0:
            return f"成功上传！输出：\n{result.stdout}"
        else:
            return f"上传失败！错误：\n{result.stderr}"
    except Exception as e:
        return f"执行命令出错：{str(e)}"

def get_local_ip():
    """
    尝试通过向公共 DNS (8.8.8.8) 建立一次 UDP 连接获取本机 IP。
    由于 UDP 不需要实际发送数据，所以不会造成额外的网络负担。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        # s.getsockname() 返回 (ip, port) 元组，这里的 ip 即本机的内网 IP
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "Unable to determine IP."
    finally:
        s.close()
    return local_ip + ":8188"

def win_path_to_wsl_path(win_path):
    """
    将 Windows 路径转换为 WSL 路径：
    - 替换盘符，如 'C:\\' -> '/mnt/c/'
    - 将所有反斜杠 '\' 替换为 '/'
    """
    # 统一将反斜杠替换为正斜杠
    if not win_path:
        raise ValueError("Input path is empty. Please provide a valid Windows path.")

    path_unix = win_path.replace("\\", "/")

    # 如果路径形如 "C:/..."（长度至少2，并且第2个字符是 ':')
    # 那么把它转为 "/mnt/c/..."
    if len(path_unix) >= 2 and path_unix[1] == ':':
        drive_letter = path_unix[0].lower()  # 例如 'c'
        path_unix = "/mnt/" + drive_letter + path_unix[2:]  # 去掉 "C:"，前面补 "/mnt/c"

    return path_unix

with gr.Blocks() as demo:
    with gr.Tabs():
        

        with gr.Tab("ivry init"):
            gr.Markdown("# Init Ivry")
            gr.Markdown("## Step 1: Login to ivry! Creat your account and enter your apikey.")
            with gr.Accordion("点击展开查看嵌入网站", open=False): 
                gr.HTML("""
                            <iframe 
                                src="https://www.ivry.co/account" 
                                width="100%" 
                                height="500" 
                                frameborder="0">
                            </iframe>
                        """)

            gr.Markdown("### 输入 API Key 来登录 Project-X")
    
            # 输入组件
            api_key_input = gr.Textbox(label="API Key", placeholder="输入你的 API Key", type="password")
            
            # 输出组件
            output_text = gr.Textbox(label="登录结果")
            
            # 按钮触发
            login_button = gr.Button("登录")
            login_button.click(run_login, inputs=api_key_input, outputs=output_text)

            gr.Markdown("## Step 2: init your app! Please give it a good name!")

            # 输入组件
            project_name_input = gr.Textbox(label="Project Name", placeholder="输入你的 Project 名字")
            
            # 输出组件
            init_output_text = gr.Textbox(label="初始化结果")
            
            # 按钮触发
            login_button = gr.Button("初始化")
            login_button.click(run_init, inputs=project_name_input, outputs=init_output_text)

            gr.Markdown("## Step 3: Go to Predict.py Generator tab to generate your predict.py!")

        with gr.Tab("Predict.py Generator"):
    
        
            options_list = ["int", "float", "str", "Path" ,"bool"]

            gr.Markdown("## Cog predict.py Generator")
            with gr.Row():
                with gr.Column():
                    dir_comfyui = gr.Textbox(label="comfy dir", placeholder="comfy dir")
                    dir_button = gr.Button("If you are windows user, please use this to convert your windows dir to wsl dir")
                    dir_button.click(win_path_to_wsl_path, inputs=dir_comfyui, outputs=dir_comfyui)
                with gr.Column():    
                    port_comfyui = gr.Textbox(label="comfyUI port",placeholder="port_comfyui", value="127.0.0.1:8188")
                    port_button = gr.Button("If you are windows user, please use your ip instead of localhost")
                    port_button.click(get_local_ip, outputs=port_comfyui)
            
            '''
            gr.Markdown("### Select an option from the list:")

            input_section = gr.Radio(choices=options_list, label="Choose one", value="Path")
            with gr.Row():
            # 创建一个Radio组件
                
                with gr.Column():
                # 创建一个显示最终选择列表的输出区域
                    output = gr.Textbox(label="Selected List", lines=5)
                    
                    # 添加按钮和交互逻辑
                    button = gr.Button("Add to List")
                    button.click(update_selection, inputs=input_section, outputs=output)

                with gr.Column():
                    gr.Markdown("### Delete an option:")
                    delete_input = gr.Dropdown(label="Select an option to delete", choices=options_list, interactive=True)
                    delete_button = gr.Button("Delete from List")
                    delete_button.click(delete_selection, inputs=delete_input, outputs=output)
                '''
            gr.Markdown("### Upload a JSON File")
            with gr.Row():
                ### workflow
                    
                
            
                # 上传组件
                file_input = gr.File(label="Upload JSON File", file_types=[".json"])
                
                # 输出组件
                json_output = gr.JSON(label="File Content (Loaded in Memory)")
                
                # 绑定上传文件和显示内容的逻辑
                file_input.change(upload_json, inputs=file_input, outputs=json_output)
                

                main_options = extract_keys(json_data)

            gr.Markdown("### Choose your inputs")
            with gr.Row():
                
            
                # 主选单
                    # 主菜单（动态更新）
                main_menu = gr.Dropdown(label="Main Menu", choices=[], interactive=True)
                
                # 次级菜单（动态更新）
                sub_menu = gr.Dropdown(label="Sub Menu (Inputs)", choices=[], interactive=True)
                    

                sub_sub_menu = gr.Dropdown(label="Sub-Sub Menu (Last Selected List)", choices=options_list, interactive=True)

                
                
            # 按钮
            submit_button = gr.Button("Submit")
                

            # 输出区域
            output_workflow = gr.Textbox(label="Result")

            # 当主选单改变时，动态更新次级选单
            main_menu.change(update_submenu, inputs=main_menu, outputs=sub_menu)

            # 提交按钮处理最终结果
            submit_button.click(process_selection, inputs=[main_menu, sub_menu, sub_sub_menu], outputs=output_workflow)
            # 删除按钮
            delete_button = gr.Button("Delete Last Line")
            
            # 按下按钮后删除最后一行
            delete_button.click(delete_last_line, inputs=output_workflow, outputs=output_workflow)



            # 上传文件后更新主菜单
            file_input.change(upload_json_and_update_menu, inputs=file_input, outputs=main_menu)
            #file_input.change(lambda _: "JSON file uploaded and main menu updated!", inputs=file_input, outputs=output_workflow)
            file_input.change(clear_cache, inputs=[], outputs=output_workflow)
            #output.change(update_subsubmenu, inputs=output, outputs=sub_sub_menu)

            
            
            


            ###
















            final_output = gr.Textbox(label="Output", interactive=False)
            generate_button = gr.Button("Generate predict.py")
            # 定义按钮点击行为
            generate_button.click(
                generate_predict_file,
                inputs=[dir_comfyui, port_comfyui, output_workflow],
                outputs=final_output
            )

        with gr.Tab("upload and host app"):
            gr.Markdown("## Step 4: upload your app, enter your project name")
            # 输入组件
            upload_name_input = gr.Textbox(label="Upload Project Name", placeholder="输入你的 Project 名字")
            
            # 输出组件
            upload_output_text = gr.Textbox(label="上传结果")
            
            # 按钮触发
            login_button = gr.Button("初始化")
            login_button.click(run_upload, inputs=upload_name_input, outputs=upload_output_text)

            gr.Markdown("## wsl notes")
            instructions = """
                # How to Install WSL and Ubuntu 20.04

                ## Step 1: Enable WSL and Virtualization Features
                1. Open **PowerShell** as Administrator.
                2. Run the following commands:
                    ```
                    dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
                    dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
                    ```
                3. Restart your computer.

                ## Step 2: Install Ubuntu 20.04
                You can install Ubuntu 20.04 in two ways:
                1. **Using Microsoft Store**:
                - Open Microsoft Store.
                - Search for "Ubuntu 20.04".
                - Click "Get" or "Install".
                2. **Using PowerShell**:
                - Run the following command:
                    ```
                    wsl --install -d Ubuntu-20.04
                    ```

                ## Step 3: Set Up Ubuntu
                1. Launch Ubuntu.
                2. Follow the on-screen instructions to set up your username and password.
                """
            gr.Markdown(instructions)

demo.launch()