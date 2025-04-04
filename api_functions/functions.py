from pydantic import BaseModel
import asyncio
import os
import requests


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
    return [urls[0]]
 

def cut_image(image):
    
    return {
        "scale": 3.14
    }

# Create a dictionary with the functions in the same file
functions = {
    'story_generator': story_generator,
    'tool_2': tool_2
}