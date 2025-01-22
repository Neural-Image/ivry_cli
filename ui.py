import gradio as gr

def generate_predict_file(dir_comfyui, port_comfyui, input_section, logic_section):
    # 读取模板文件内容
    with open("src/templates/predict_comfyui_ui.py", "r") as template_file:
        content = template_file.read()

    # 替换模板中的占位符
    content = content.replace("{{dir_comfyui}}", dir_comfyui)
    content = content.replace("{{port_comfyui}}", port_comfyui)
    content = content.replace("{{input_section}}", input_section)
    content = content.replace("{{logic_section}}", logic_section)

    # 保存为 predict.py
    with open("gradio_predict.py", "w") as predict_file:
        predict_file.write(content)

    return "predict.py generated successfully!"

# 定义 Gradio UI
with gr.Blocks() as demo:
    gr.Markdown("## Cog predict.py Generator")
    dir_comfyui = gr.Textbox(label="comfy dir", placeholder="comfy dir")
    port_comfyui = gr.TextArea(
        label="Input Section",
        placeholder="port_comfyui"
    )
    input_section = gr.TextArea(
        label="Logic Section",
        placeholder="input_section."
    )
    logic_section = gr.TextArea(
        label="Output Statement",
        placeholder="logic_section."
    )
    output = gr.Textbox(label="Output", interactive=False)

    generate_button = gr.Button("Generate predict.py")

    # 定义按钮点击行为
    generate_button.click(
        generate_predict_file,
        inputs=[dir_comfyui, port_comfyui, input_section, logic_section],
        outputs=output
    )

demo.launch()