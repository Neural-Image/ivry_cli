import requests
import json

url = "https://test-pc.neuralimage.net/pc/client-api/predict_signature/"

payload = json.dumps({
  "inputs": [
    {
      "name": "prompt",
      "type": "str",
      "validation": {
        "description": "this is a prompt"
      }
    },
    {
      "name": "seed",
      "type": "int",
      "validation": {
        "description": "seed"
      }
    },
    {
      "name": "steps",
      "type": "int",
      "validation": {
        "default": "50",
        "description": "steps",
        "ge": "0",
        "le": "1000"
      }
    },
    {
      "name": "guidance_scale",
      "type": "float",
      "validation": {
        "default": "5.0",
        "description": "guidance_scale",
        "ge": "0",
        "le": "20"
      }
    }
  ],
  "outputs": "list[Path]"
})

#页面获取
apikey = '1870047274106617856'

headers = {
   'X-API-KEY': apikey,
   'Content-Type': 'application/json',
}

response = requests.request("POST", url, headers=headers, data=payload)
json_data = response.json()
print(json_data.get("httpStatus"))
print(json_data.get("data"))
