# 客户端流程测试

## 业务端API

### 客户端-上传模版
```
/pc/client-api/upload/file
```
1. 服务器收到一[json](#predict_signature-json)
1. 创建一个**id**
1. 存储[json](#predict_signature-json)并关联**id**
1. cloudflare 创建一个tunnel, 使用[cloudflare_api.py](../../src/cloudflare_api.py)里的create_tunnel(**id**)，并存储[返回结果的内容](#存储create_tunnel返回内容)，关联**id**
1. cloudflare 使用**id**为tunnel创建一个dns_records, 使用[cloudflare_api.py](../../src/cloudflare_api.py)里的create_hostname(**id**, target_content)。target_content为`<TunnelID>.cfargotunnel.com`，TunnelID在上一步获得
1. [以json形式返回结果](#json返回)
    - ❗️不使用之前讨论的使用后续api call分别获得credential和config文件，改用json返回

#### Note
- 所需cloudflare api key通过微信发送

#### Task
- endpoint改成`/pc/client-api/predict_signature`
- ❗️改为传输json不再上传yaml文件
- 写一个调用的python例子保存在workflow_test/python下面，命名为predict_signature.py
- 添加配套修改用的endpoint: `/pc/client-api/predict_signature/{id}`

#### predict_signature json
```
{
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
}
```

#### 存储create_tunnel返回内容
```
{
    "success": True,
    "errors": [],
    "messages": [],
    "result": {
        "id": "c81feca1-77be-450a-91da-610d5b4021cd",
        "account_tag": "6a1a4cddaf1505b8915135791244703e",
        "created_at": "2024-12-25T05:46:03.607999Z",
        "deleted_at": None,
        "name": "...",
        "connections": [],
        "conns_active_at": None,
        "conns_inactive_at": "2024-12-25T05:46:03.607999Z",
        "tun_type": "cfd_tunnel",
        "metadata": {},
        "status": "inactive",
        "remote_config": False,
        "credentials_file": {
            "AccountTag": <需要保存>,
            "TunnelID": <需要保存>,
            "TunnelName": <需要保存>,
            "TunnelSecret": <需要保存>,
        },
        "token": <需要保存>
    },
}

```
#### json返回
```
{
    "credential": {
        "AccountTag": "...", # 参见4
        "TunnelID": "...",
        "TunnelName": "...",
        "token": "..."
    }
    "config": {
        "tunnel": "<TunnelID>",
        "credentials-file": "tunnel_credential.json",
        "ingress": [
            {
                "hostname": "<id>.lormul.org",
                "service": "http://localhost:3009"
            },
            {
                "service": "http_status:404"
            }
        ]
    }
}
```

### 客户端-获取cloudflare credential
```
/pc/client-api/upload/credential
```
❗️deprecate，合并至“客户端-上传模版”

### 客户端-上传output_file
```
/pc/client-api/upload/output/{id}
```
#### Task
- endpoint改为put `/pc/client-api/upload/{file_name}`
    - filename 由"{prediction_id}_{id}_{filename}"组成，见以下代码
    - prediction_id即为当前/pc/client-api/upload/output/{id}中的id
    - prediction_id可由headers["X-Prediction-ID"]获取
- endpoint改为支持以下put_file_to_signed_endpoint()的方式
    - 注意使用put，而不是post

见[files.py](../../src/cog/files.py)
```
def put_file_to_signed_endpoint(
    fh: io.IOBase, endpoint: str, client: requests.Session, prediction_id: Optional[str], id: str
) -> str:
    if fh.seekable():
        fh.seek(0)

    filename = guess_filename(fh)
    content_type, _ = mimetypes.guess_type(filename)

    # set connect timeout to slightly more than a multiple of 3 to avoid
    # aligning perfectly with TCP retransmission timer
    connect_timeout = 10
    read_timeout = 15

    headers = {
        "Content-Type": content_type,
    }
    if prediction_id is not None:
        headers["X-Prediction-ID"] = prediction_id

    resp = client.put(
        ensure_trailing_slash(endpoint) + f"{prediction_id}_{id}_{filename}",
        fh,  # type: ignore
        headers=headers,
        timeout=(connect_timeout, read_timeout),
    )
    resp.raise_for_status()

    # Try to extract the final asset URL from the `Location` header
    # otherwise fallback to the URL of the final request.
    final_url = resp.url
    if "location" in resp.headers:
        final_url = resp.headers.get("location")

    # strip any signing gubbins from the URL
    return str(urlparse(final_url)._replace(query="").geturl())
```

### 客户端-回传进度
```
/pc/client-api/upload/progress/{id}
```
#### Task
- endpoint改为`/pc/client-api/webhook/prediction`
- 传输的内容见以下json，所有字段全部存储并关联至prediction_id

```
# processing状态
{
    "input": {
        "prompt": "a photo of sprite",
        "seed": 76551,
        "steps": 50,
        "guidance_scale": 5.0
    },
    "output": null,
    "id": "7", # 即为prediction_id
    "created_at": "2024-12-06T00:20:04.185000+00:00",
    "started_at": "2024-12-23T22:52:01.460145+00:00",
    "logs": "",
    "status": "processing"
}

# succeeded状态
{
    "input": {
        "prompt": "a photo of sprite",
        "seed": 76551,
        "steps": 50,
        "guidance_scale": 5.0
    },
    "output": [
        "http://localhost:3010/upload_file/ComfyUI_00031_.png",
        "http://localhost:3010/upload_file/ComfyUI_00031_.png"
    ],
    "id": "7", # 即为prediction_id
    "created_at": "2024-12-06T00:20:04.185000+00:00",
    "started_at": "2024-12-23T22:52:01.460145+00:00",
    "completed_at": "2024-12-23T22:52:08.814683+00:00",
    "logs": "",
    "status": "succeeded",
    "metrics": {
        "predict_time": 7.354538
    }
}
```

### 客户端-回传进度(to implement)
```
/pc/client-api/models
```
返回用户所有的model，基本信息包含model name， model id