import requests

url = "https://test-pc.neuralimage.net/pc/client-api/upload/output/1"

payload={}
files=[
   ('file',('dengchao.png',open('upTAgMAHQe2SJTPy0UKUhA.jpeg','rb'),'image/png'))
]

response = requests.request("POST", url, files=files)

print(response.text)