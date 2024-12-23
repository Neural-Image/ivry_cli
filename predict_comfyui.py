from cog import BasePredictor, Input, Path 
import tempfile
from PIL import Image
from time import sleep

import websocket #NOTE: websocket-client (https://github.com/websocket-client/websocket-client)
import uuid
import json
import os
from websocket_comfyui import get_images, queue_prompt, get_history 
from typing import List

from dotenv import load_dotenv
load_dotenv()

COMFYUI_PATH = os.environ.get("COMFYUI_PATH", "")
server_address = "127.0.0.1:8188"

class Predictor(BasePredictor):
    def setup(self):
        pass
    def predict(self,
                prompt: str = Input(description="this is a prompt"),
                seed: int = Input(description="seed"),
                steps: int = Input(default=50, ge=0, le=1000, description="steps"),
                guidance_scale: float = Input(default=5.0, ge=0, le=20, description="guidance_scale"),
    ) -> Path:
        client_id = str(uuid.uuid4())
        prompt_text = """
        {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "cfg": 8,
                    "denoise": 1,
                    "latent_image": [
                        "5",
                        0
                    ],
                    "model": [
                        "4",
                        0
                    ],
                    "negative": [
                        "7",
                        0
                    ],
                    "positive": [
                        "6",
                        0
                    ],
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "seed": 8566257,
                    "steps": 20
                }
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "v1-5-pruned-emaonly-fp16.safetensors"
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "batch_size": 1,
                    "height": 512,
                    "width": 512
                }
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": [
                        "4",
                        1
                    ],
                    "text": "masterpiece best quality girl"
                }
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": [
                        "4",
                        1
                    ],
                    "text": "bad hands"
                }
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": [
                        "3",
                        0
                    ],
                    "vae": [
                        "4",
                        2
                    ]
                }
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "ComfyUI",
                    "images": [
                        "8",
                        0
                    ]
                }
            }
        }
        """   

        prompt_config = json.loads(prompt_text)
        #set the text prompt for our positive CLIPTextEncode
        prompt_config["6"]["inputs"]["text"] = prompt

        #set the seed for our KSampler node
        prompt_config["3"]["inputs"]["seed"] = seed
        ws = websocket.WebSocket()
        ws.connect("ws://{}/ws?clientId={}".format(server_address, client_id))
        images = get_images(ws, client_id, prompt_config)

        ws.close()           
        img_path_list = []
        for node_id in images:
            for image_path in images[node_id]:
                img_path_list.append(image_path)
        output_path_list = [Path(os.path.join(COMFYUI_PATH, "output", p)) for p in img_path_list] 
        return output_path_list[0]
