# Updated ivry_cli Documentation

## 🔥 Updates
- **2025/03/12**: Support python creators
- **2025/03/07**: Fixed issues with `run_server` command, now using direct subprocess approach 
- **2025/03/07**: Added troubleshooting section for common errors
- **2025/03/07**: Added new `list_apps` command to view all your applications
- **2025/02/27**: ivry_cli pulling capabilities added
- **2025/02/26**: WebUI updates:
  - Find ComfyUI information
  - Better UI experience
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
   git clone https://github.com/your-repo/ivry_cli.git
   cd ivry_cli
   ```
2. Install the CLI:
   ```bash
   pip install -e .
   ```

---
# Steps to host your app on ivry

# For python creators:

## 1.  Authentication

1. Retrieve your API key from our website.
2. Login using the CLI:
   ```bash
   ivry_cli login --auth_token {your_apikey}
   ```
## 2. Create your predict.py 

save your predict.py in 

ivry_cli
  - predict.py
  - src
  - comfyui_workflows
  - docs

## 3. generate your predict_signature.json

 ```bash
 ivry_cli parse_predict 
 ```
it will generate a predict_signature.json file. We will use it in the next step

## 4. Create your app on ivry website

upload your predict_signature.json

## 5. Pull your app to cli

```bash
ivry_cli pull_project --app_id your_app_id
```
for example:
ivry_cli pull_project --app_id 66


## 6. Host your app

Start both the ivry_cli model server and cloudflared tunnel with a single command:

```bash
ivry_cli run_server --force
```

### Specify a different project path

```bash
ivry_cli run_server --project project_folder_name --force #like app_30
```

### Stopping the Server

```bash
# Stop all running ivry services
ivry_cli stop_server [--project_path PATH] [--force]
```

The `--force` option allows you to terminate services that may be stuck or not responding to normal shutdown commands.



# For ComfyUI creators:

## 1.  Authentication

1. Retrieve your API key from our website.
2. Login using the CLI:
   ```bash
   ivry_cli login --auth_token {your_apikey}
   ```

## 2. Create your app on ivry website

## 3. Pull your app to cli

Befor do that, make sure you start your comfyUI. make sure you have --listen for it
or
You need to pass your comfyUI directory

```bash
ivry_cli pull_project --app_id your_app_id --comfui_port default_is_8188
```
for example:
ivry_cli pull_project --app_id 66 # if your are using default settings for comfyUI

or
```bash
ivry_cli pull_project --app_id your_app_id --comfui_port default_is_8188 --comfyUI_dir path_to_your_comfyUI
```

---

## 4. Hosting Your Project

Start both the ivry_cli model server and cloudflared tunnel with a single command:

```bash
ivry_cli run_server --force
```

### Specify a different project path

```bash
ivry_cli run_server --project project_folder_name --force #like app_30
```

### Stopping the Server

```bash
# Stop all running ivry services
ivry_cli stop_server [--project_path PATH] [--force]
```

The `--force` option allows you to terminate services that may be stuck or not responding to normal shutdown commands.

### Traditional Method (Still Supported)

If you prefer to start the services separately:

```bash
# Start the ivry_cli model server
cd {project_name}
ivry_cli start model --upload-url=https://www.lormul.org/pc/client-api/upload

# In another terminal, start the cloudflared tunnel
cd {project_name}
cloudflared tunnel --config tunnel_config.json run
```

---

## Finding ComfyUI Information

To identify your ComfyUI installation path and port:

```bash
ivry_cli find_comfyUI
```

This will detect any running ComfyUI instances and display:
- Process ID and name
- Installation path
- Listening port

---

## Troubleshooting

### Module Not Found Error
If you see "No module named ivry_cli" errors when using `run_server`, make sure you have correctly installed the package:
```bash
pip install -e .
```
And that your environment variables are correctly set up.

### WebSocket Issues
If you encounter WebSocket errors when starting the server, try:
```bash
pip uninstall websockets
pip install websocket-client
```

### Connection Problems
If you're having trouble connecting to the server, check:
1. Your API key is valid and correctly entered
2. Your network connection is stable
3. The server is accessible from your location

### Log Files
Check these log files for troubleshooting:
- `logs/ivry_server.log`: Application runtime logs
- `logs/cloudflared.log`: CloudFlare tunnel logs

### Processes Won't Stop
If you're having trouble stopping processes:
```bash
# Use the force flag
ivry_cli stop_server --force

# Or manually kill processes
ps aux | grep ivry_cli
ps aux | grep cloudflared
# Then use the PIDs to terminate them
kill <PID>
```

### Port Already in Use
If you see "Port 3009 is already in use" errors:
1. Check for running ivry processes: `ps aux | grep ivry`
2. Stop any running processes: `ivry_cli stop_server --force`
3. If needed, manually kill the process using the port: `lsof -i:3009` then `kill <PID>`

---

### Completed Tasks:
✅ update parse_inout for python project
      - must follow current syntax, must has default values, also with optional values
      - can edit either webite or local
✅ python process
✅ Support web pull
✅ WSL2 package
✅ Heartbeat sending improvements
✅ Background running mode using direct subprocess approach  
✅ Find ComfyUI function in WebUI  
✅ Windows version support  
✅ List applications command  
✅ Improved command-line options for `run_server`  
✅ Enhanced template code for ComfyUI  
✅ Cloudflare research & configuration validation  
✅ `ivry_cli stop` command  
✅ Expanded testing templates  
✅ Eliminated unnecessary file generation  
✅ Improved `upload/update` command-line experience  
✅ Log truncation (Completed on 2025/01/20)  
✅ Logging interval configuration (Completed on 2025/01/20)  
✅ Organized hyperparameters (Completed on 2025/01/20)  

---

For more details, visit our documentation or reach out via support channels!
