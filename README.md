# Project-X Documentation

## 🔥 Updates
- **2025/02/26**: WebUI updates:
  - Find ComfyUI information
  - better UI
- **2025/02/08**: WebUI updates:
  - Input type validation
  - Log monitor
- **2025/01/29**: WebUI updates:
  - Inputs renamed
  - Workflow API JSON validation
  - Duplicate input check
- **2025/01/28**: WebUI Windows version (TODO: Update app, signature JSON)
- **2025/01/23**: WebUI Beta release
- **2025/01/20**: Logging improvements:
  - Log truncation (holds latest 5MB logs)
  - Default logging interval set to 1 second
  - Organized hyperparameters (Website URL)

### Windows Users
For installation instructions on Windows, refer to: [Windows Installation Guide](docs/workflow_test/wsl2.md)

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo/project-x.git
   cd project-x
   ```
2. Install the CLI:
   ```bash
   cd ivry_cli
   pip install -e .
   ```

---

## Authentication

1. Retrieve your API key from our website.
2. Login using the CLI:
   ```bash
   project-x login --auth_token {your_apikey}
   ```

---

## Initializing a Project

Currently, the CLI supports two modes: `comfyui` and `model`.

```bash
project-x init_app --project_name {project_name} --mode {comfyui/model}
```

### Examples:
- For **ComfyUI**:
  ```bash
  project-x init_app --project_name my_project --mode comfyui
  ```
- For **Model-based projects**:
  ```bash
  project-x init_app --project_name my_project --mode model
  ```

Once initialized, a project folder is created, and a `predict.py` file will be available. Edit `predict.py` according to your model or workflow requirements.

---

## Uploading Your Project

### Important: Use Absolute Paths in `predict.py`

Your `predict.py` file is located under:
```bash
/ivry_cli/{project_name}/predict.py
```
Modify the script as needed, following the provided comments, and then upload your app:

```bash
project-x upload_app --model_name {project_name}
```
Or navigate to the project directory and execute:
```bash
cd {project_name}
project-x upload_app
```

---

## Managing Your Model

### Check Uploaded Models
```bash
project-x list_models
```

### Update an Existing Model
If you update `predict.py` after uploading, you can update your model:
```bash
project-x update_app --model_id {model_id} --model_name {project_name}
```
Or use:
```bash
cd {project_name}
project-x update_app --model_id {model_id}
```

---

## Hosting Your Project

### Start the Server
#### Linux:
```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
dpkg -i cloudflared-linux-amd64.deb
```
#### macOS:
```bash
brew install cloudflare/cloudflare/cloudflared
```
#### Start the Project:
```bash
cd {project_name}
project-x start_server
```

### Stop the Server
```bash
project-x stop_server
```

---

## Troubleshooting

### WebSocket Issues
If you encounter WebSocket errors when starting the server, try:
```bash
pip uninstall websockets
pip install websocket-client
```

---

## TODOs

- [ ] Implement find comfyUI function in webui
- [ ] Support web pull
- [ ] wsl2 package
- [ ] heartbeat sending 


### Completed Tasks:
✅ Windows version support  
✅ Improved command-line options for `start_server`  
✅ Enhanced template code for ComfyUI  
✅ Cloudflare research & configuration validation  
✅ `project-x stop` command  
✅ Expanded testing templates  
✅ Eliminated unnecessary file generation  
✅ Improved `upload/update` command-line experience  
✅ Log truncation (Completed on 2025/01/20)  
✅ Logging interval configuration (Completed on 2025/01/20)  
✅ Organized hyperparameters (Completed on 2025/01/20)  

---

For more details, visit our documentation or reach out via support channels!
