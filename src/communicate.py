import base64
import io
import mimetypes
import os
from typing import Optional
from urllib.parse import urlparse

import requests

def upload_config():
    # auth_token = "N2QxYzY5NjQ3YWJmZTc2NGY3ZjAzOWU1Y2YwMGI1MmIxNTliZTYwMTI5ZDJkY2UxYTI3MzVkOTkwNzRkZThiM18x"
    headers = {
    'Authorization': 'Bearer N2QxYzY5NjQ3YWJmZTc2NGY3ZjAzOWU1Y2YwMGI1MmIxNTliZTYwMTI5ZDJkY2UxYTI3MzVkOTkwNzRkZThiM18x',
    'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
    'Accept': '*/*',
    'Host': 'test-pc.neuralimage.net',
    'Connection': 'keep-alive',
    'Content-Type': 'multipart/form-data; boundary=--------------------------509142127009424983488282'
    }    
    files=[
    ('file',('InTypeOutType.yaml', open('InTypeOutType.yaml','rb'),'application/octet-stream'))
    ]    
    payload={"identity":"InTypeOutType.yaml","templateName":"这是模版名称","templateCover":"这是模版封面","description":"这是模版描述","serversPath":"这是模版调用地址"}
    resp = requests.post(
        "http://52.53.132.109:8083/pc/client-api/upload/file",
        files=files,
        data=payload,
        headers=headers,
        timeout=100)
    resp.raise_for_status()
    print(resp)    

    # with open("InTypeOutType.yaml", 'rb') as f:
    #     resp = requests.post(
    #         "http://52.53.132.109:8083/pc/client-api/upload/file",
    #         files=files,
    #         data=payload,
    #         headers=headers,
    #         timeout=5 )
    #     resp.raise_for_status()
    #     print(resp)