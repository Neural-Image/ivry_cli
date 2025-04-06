from pydantic import BaseModel
import asyncio
import os
import requests
from pathlib import Path
from openai import OpenAI
from PIL import Image
from io import BytesIO


def prompt_generator(prompt):
    api_key = "sk-proj-U5bRRw2dz9uYLKi2Vh4ET3BlbkFJEaMqgvT8HCeb2UDfzF0b"
    client = OpenAI(api_key=api_key)

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "developer", "content": "You are a four scene comic story generator."},
            {"role": "user", "content": f"Generate a 4 scene O-Henry style story about {prompt}. Then, generate 4 Midjourney image prompts for illustrating the story. Combine the prompts into one single-shot image in following structure: 'A comic consists of 4 scenes. Up left: image prompt 1, Up right: image prompt 2, Down left: image prompt 3, Down right: image prompt 4.' The story should have a O Henry style. Return the result as single line json."}
        ]
        )
    result = completion.choices[0].message
    result = result.content
    #print(result)
    #print(type(result))
    return result

def story_generator(prompt):
    api_key = "sk-proj-U5bRRw2dz9uYLKi2Vh4ET3BlbkFJEaMqgvT8HCeb2UDfzF0b"
    if not api_key:
        raise ValueError("请设置环境变量 OPENAI_API_KEY")

    url = "https://api.openai.com/v1/images/generations"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": "dall-e-3",
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024"
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()  # 如果请求失败会抛出异常
    result = response.json()
    urls = [item["url"] for item in result.get("data", [])]
    response = requests.get(urls[0])
    if response.status_code == 200:
        # 定义保存的本地文件路径
        local_file = Path("downloaded_image.png")
        # 将响应的二进制内容写入文件
        local_file.write_bytes(response.content)
    return [local_file]
 

def cut_image(image_url):
    
    response = requests.get(image_url)
    if response.status_code != 200:
        raise Exception(f"下载图片失败，状态码：{response.status_code}")
    
    # 读取图片
    img = Image.open(BytesIO(response.content))
    width, height = img.size
    
    # 计算水平和垂直的中点（这里使用整除，若尺寸不均匀，最后一块可能略大）
    half_width = width // 2
    half_height = height // 2
    
    # 定义四个区域的裁剪框
    boxes = [
        (0, 0, half_width, half_height),               # 左上角
        (half_width, 0, width, half_height),             # 右上角
        (0, half_height, half_width, height),            # 左下角
        (half_width, half_height, width, height)         # 右下角
    ]
    
    output_paths = []
    for i, box in enumerate(boxes, start=1):
        quadrant_img = img.crop(box)
        # 定义保存文件的路径（此处保存为 PNG 文件）
        output_path = Path(f"image_quadrant_{i}.png")
        quadrant_img.save(output_path)
        output_paths.append(output_path.resolve())
    
    return output_paths
    

# Create a dictionary with the functions in the same file
functions = {
    'story_generator': story_generator,
    'cut_image': cut_image,
    "prompt_generator": prompt_generator
}