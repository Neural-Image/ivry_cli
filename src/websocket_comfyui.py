#This is an example that uses the websockets api to know when a prompt execution is done
#Once the prompt execution is done it downloads the images using the /history endpoint

import json
import urllib.request
import urllib.parse
import logging
import time

server_address = "127.0.0.1:8188"
LOG_FILE = "client.log"
MIN_INTERVAL = 1  # 最小间隔时间


def queue_prompt(prompt, client_id):
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req =  urllib.request.Request("http://{}/prompt".format(server_address), data=data)
    return json.loads(urllib.request.urlopen(req).read())

def get_image(filename, subfolder, folder_type):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen("http://{}/view?{}".format(server_address, url_values)) as response:
        return response.read()

def get_history(prompt_id):
    with urllib.request.urlopen("http://{}/history/{}".format(server_address, prompt_id)) as response:
        return json.loads(response.read())

def get_images(ws, client_id, prompt):
    prompt_id = queue_prompt(prompt, client_id)['prompt_id']
    output_images = {}
    logging.basicConfig(
        level=logging.INFO,  # 设置日志级别为 INFO
        format="%(asctime)s - %(levelname)s - %(message)s",  # 日志格式
        handlers=[
            logging.FileHandler(LOG_FILE),  # 输出到 client.log 文件
            logging.StreamHandler()  # 同时输出到控制台（可选）
        ]
    )
    logger = logging.getLogger("predict_logger")
    last_print_time = 0 
    while True:
        out = ws.recv()
        current_time = time.time()
        if isinstance(out, str):
            if current_time - last_print_time >= MIN_INTERVAL:
                logger.info(out) 
                last_print_time = current_time
            message = json.loads(out)
            if message['type'] == 'executing':
                data = message['data']
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break #Execution is done
        else:
            # If you want to be able to decode the binary stream for latent previews, here is how you can do it:
            # bytesIO = BytesIO(out[8:])
            # preview_image = Image.open(bytesIO) # This is your preview in PIL image format, store it in a global
            continue #previews are binary data

    history = get_history(prompt_id)[prompt_id]
    #NOTE original code 
    # for node_id in history['outputs']:
    #     node_output = history['outputs'][node_id]
    #     images_output = []
    #     if 'images' in node_output:
    #         for image in node_output['images']:
    #             image_data = get_image(image['filename'], image['subfolder'], image['type'])
    #             images_output.append(image_data)
    #     output_images[node_id] = images_output
    #print('history :', history)
    for node_id in history['outputs']:
        node_output = history['outputs'][node_id]
        images_output = []
        if 'images' in node_output:
            for image in node_output['images']:
                images_output.append(image['filename'])
        if 'gifs' in node_output:
            for image in node_output['gifs']:
                images_output.append(image['filename'])
        if 'videos' in node_output:
            for image in node_output['videos']:
                images_output.append(image['filename'])
        output_images[node_id] = images_output        

    return output_images



#Commented out code to display the output images:

# for node_id in images:
#     for image_data in images[node_id]:
#         from PIL import Image
#         import io
#         image = Image.open(io.BytesIO(image_data))
#         image.show()

