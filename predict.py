from cog import BasePredictor, Input, Path 
import tempfile
from PIL import Image
from time import sleep
import requests
import random
import websocket #NOTE: websocket-client (https://github.com/websocket-client/websocket-client)
import uuid
import json
import os
from websocket_comfyui import get_images, queue_prompt, get_history 
from typing import List

from dotenv import load_dotenv
load_dotenv()

# 1.Please put your comfyUI path here:
COMFYUI_PATH = '/Users/steveyang/Desktop/ComfyUI'
# 2.Please put your comfyUI port here: (by defalut is 127.0.0.1:8188 if you run "python main.py --listen")
server_address = '127.0.0.1:8188'


class Predictor(BasePredictor):
    def setup(self):
        pass

    

    # 3.put your inputs here:
    """
    put the inputs of your app here: 
    some common inputs:
        image: Path = Input(description="Grayscale input image"),
        prompt: str = Input(default="hello", max_length=1000, description="this is a prompt"),
        steps: int = Input(default=50, ge=0, le=1000, description="steps"),
        guidance_scale: float = Input(default=5.0, ge=0, le=20, description="guidance_scale"),
    """
    def predict(self,
                prompt: str= Input(description=''),
                neg_prompt: str= Input(description=''),
                
    ) -> Path:
        client_id = str(uuid.uuid4())
        # 4.put your workflow api path here:
        workflow_file = r'/Users/steveyang/Desktop/ivry_cli/comfyui_workflows/226test.json'


        with open(workflow_file, 'r', encoding="utf-8") as workflow_file:
            prompt_config = json.load(workflow_file)

        # 5.put the input nodes here
        '''
        In this example, only node[326] and node[518] are inputs node for users. node[658] and node[639] are taking assets for some usecases like ip-adapter
        '''
        prompt_config['7']['inputs']['text'] = prompt
        prompt_config['6']['inputs']['text'] = neg_prompt
        

        '''
        If your output node is not from comfy core, you need to define an output path 
        
        promtp_config["xxx"]["inputs"]["filename_prefix"] = path/to/your/output/file
        '''


        # This part random seeds for every nodes that uses seed, if you don't want that just delete this part
        for node_id, node in prompt_config.items():
            inputs = node.get("inputs", {})
            seed_keys = ["seed", "noise_seed", "rand_seed"]
            for seed_key in seed_keys:
                if seed_key in inputs and isinstance(inputs[seed_key], (int, float)):
                    new_seed = random.randint(0, 2**32 - 1)
                    print(f"Randomising {seed_key} to {new_seed}")
                    inputs[seed_key] = new_seed

        # This part is running comfyUI with your workflow
        ws = websocket.WebSocket()
        ws.connect("ws://{}/ws?clientId={}".format(server_address, client_id))
        # If your output is image with comfy Core node:
        images = get_images(ws, client_id, prompt_config, server_address)
        ws.close()
        print('inference done')
        img_path_list = []
        for node_id in images:
            for image_path in images[node_id]:
                img_path_list.append(image_path)
        output_path_list = [Path(os.path.join(COMFYUI_PATH, "output", p)) for p in img_path_list]
        print("output_path_list", output_path_list)
        # If your output is video or image without comfy Core Node:
        '''
        # Define a output path for the result:


        '''
        valid_outputs = [file for file in output_path_list if os.path.isfile(file)]


        return valid_outputs 
