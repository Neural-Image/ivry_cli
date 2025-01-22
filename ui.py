import gradio as gr

import ast
import json

json_data = {}
final_selection = []
inputs_counter = {
    "int":0, 
    "float":0, 
    "str":0, 
    "Path":0 ,
    "bool":0
}

def generate_predict_file(dir_comfyui, port_comfyui, input_section, logic_section):
    # 读取模板文件内容
    input_parameter = ""
    with open("src/templates/predict_comfyui_ui.py", "r") as template_file:
        content = template_file.read()
    print(input_section)
    input_section = ast.literal_eval(input_section)

    ### Inputs 


    for i in input_section:
        input_parameter = input_parameter + str(i) + ": " + str(i).split("_")[0] + "= Input(description='user input image'),\n                "  
    print(input_parameter)
    
    ###

    ### workflow json









    ###
    
    
    
    
    
    
    
    
    
    # 替换模板中的占位符
    content = content.replace("{{dir_comfyui}}", dir_comfyui)
    content = content.replace("{{port_comfyui}}", port_comfyui)
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
    return f"Main Selection: {main_selection}, Sub Selection: {sub_selection}, Sub-Sub Selection: {sub_sub_selection}"

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


# 定义 Gradio UI
with gr.Blocks() as demo:
    options_list = ["int", "float", "str", "Path" ,"bool"]

    gr.Markdown("## Cog predict.py Generator")
    with gr.Row():
        dir_comfyui = gr.Textbox(label="comfy dir", placeholder="comfy dir")
    #with gr.Row():
        port_comfyui = gr.Textbox(label="comfyUI port",placeholder="port_comfyui")
        logic_section = gr.Textbox(label="logic_section port",placeholder="port_comfyui")


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


        ### workflow
            
        gr.Markdown("### Upload a JSON File")
    
        # 上传组件
        file_input = gr.File(label="Upload JSON File", file_types=[".json"])
        
        # 输出组件
        json_output = gr.JSON(label="File Content (Loaded in Memory)")
        
        # 绑定上传文件和显示内容的逻辑
        file_input.change(upload_json, inputs=file_input, outputs=json_output)
        

        main_options = extract_keys(json_data)


        gr.Markdown("### Dynamic Submenu Example")
    
        # 主选单
            # 主菜单（动态更新）
        main_menu = gr.Dropdown(label="Main Menu", choices=[], interactive=True)
        
        # 次级菜单（动态更新）
        sub_menu = gr.Dropdown(label="Sub Menu (Inputs)", choices=[], interactive=True)
            

        sub_sub_menu = gr.Dropdown(label="Sub-Sub Menu (Last Selected List)", choices=[], interactive=True)

        # 输出区域
        output_workflow = gr.Textbox(label="Result")
        
        # 按钮
        submit_button = gr.Button("Submit")
        
        # 当主选单改变时，动态更新次级选单
        main_menu.change(update_submenu, inputs=main_menu, outputs=sub_menu)

        # 次级菜单变化后显示结果
        sub_menu.change(lambda x: f"You selected: {x}", inputs=sub_menu, outputs=output_workflow)



        # 提交按钮处理最终结果
        submit_button.click(process_selection, inputs=[main_menu, sub_menu, sub_sub_menu], outputs=output_workflow)

        # 上传文件后更新主菜单
        file_input.change(upload_json_and_update_menu, inputs=file_input, outputs=main_menu)
        file_input.change(lambda _: "JSON file uploaded and main menu updated!", inputs=file_input, outputs=output_workflow)
        output.change(update_subsubmenu, inputs=output, outputs=sub_sub_menu)



        ###
















    final_output = gr.Textbox(label="Output", interactive=False)
    generate_button = gr.Button("Generate predict.py")
    # 定义按钮点击行为
    generate_button.click(
        generate_predict_file,
        inputs=[dir_comfyui, port_comfyui, output, logic_section],
        outputs=final_output
    )
demo.launch()