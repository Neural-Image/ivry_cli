## Installation
1. clone the repo
2. install the cli:
```bash
cd ivry_cli
pip install -e .
```

## Login from cli
1. get your apikey from our website
2. login by cli:
```bash
project-x login --auth_token {your_apikey}
```

## Init your app
Current version support --mode comfyui/model
```bash
project-x init_app --project_name {project name} --mode {comfyui/model} #example: project-x init_app --project_name colab_test --mode model
```
if you are using comfyUI:
```bash
project-x init_app --project_name {project name} --mode comfyui
```

if you are using model:
```bash
project-x init_app --project_name {project name} --mode model
```

Your project folder should generated, and you can find predict.py in it. Next step is to edit predict.py based on your workflow or model.


## Upload your app
`TODO: add cd to dir version`
# Please put absolute dir in predict.py #

Your predict.py location is under /ivry_cli/{project name}/predict.py 
You need to edit it based on the comments
After you finish editing 'predict.py' in your project, you can upload your app to our website:

```bash
project-x upload_app --model_name {project name} #example: colab_test
```
or
```bash
cd {project name}
project-x upload_app
```

## Check your model status
You can check your uploaded models on our websites:
```bash
project-x list_models
```
## OPTIONS: update your app if you changed your predict.py after uploaded:
```bash
project-x update_app --model_id {model_id} --model_name {project name} #example: project-x update_app --model_id ivrymodel67 --model_name colab_test
```
or
```bash
cd {project name}
project-x update_app --model_id {model_id}
```


## Start to host your app
start your app:
```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
dpkg -i cloudflared-linux-amd64.deb
cd {project name}
project-x start_server
```
stop your app:
```bash
project-x stop_server
```

## TODO:
**1. windows version**

~~2. better command lines for start server~~

**3. better template code for comfyUI**

~~4. cloudflare 使用方法研究，为什么 buffersize不够还是可以用。 config.json 是否存在问题？~~

~~5. project-x stop~~

**6. cloudflare 验证，cloudflare 调用用户本机验证**
   
**7. more templates to test**
   
**8. minor bugs: a. stop generate unnessasary files**

~~9. better command lines for upload/update server~~
