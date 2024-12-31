# installation
1. clone the repo
2. install the cli:
```bash
cd ivry_cli
pip install -e .
```

# Login from cli
1. get your apikey from our website
2. login by cli:
```bash
project-x login --auth_token {your_apikey}
```

### Init your app
Current version support --mode comfyui/model
```bash
project-x init_app --project_name {project name} --mode {your app mode} #example: project-x init_app --project_name colab_test --mode model
```

### Upload your app
`TODO: add cd to dir version`
After you finish editing 'predict.py' in your project, you can upload your app to our website:
```bash
project-x upload_app --model_name {project name} #example: colab_test
```

### Check your model status
You can check your uploaded models on our websites:
```bash
project-x list_models
```
### OPTIONS: update your app if you changed your predict.py after uploaded:
```bash
project-x update_app --model_id {model_id} --model_name {project name} #example: project-x update_app --model_id ivrymodel67 --model_name colab_test
```

### Start to host your app
`TODO: add a new command for start app + start cloudflare`
1. start your app:
```bash
cd {project name}
project-x start model --upload-url=https://test-pc.neuralimage.net/pc/client-api/upload
```
2. start cloudflare
```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
dpkg -i cloudflared-linux-amd64.deb
cloudflared tunnel --config tunnel_config.json run 7a32c54f-f326-40a5-8984-0ab49798562f
```

