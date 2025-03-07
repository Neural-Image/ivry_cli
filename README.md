# ivry_cli Documentation

## 🔥 Updates
- **2025/03/07**: Added new `run_server` command with background processing options
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

## Authentication

1. Retrieve your API key from our website.
2. Login using the CLI:
   ```bash
   ivry_cli login --auth_token {your_apikey}
   ```

---

## Initializing a Project

Currently, the CLI supports two modes: `comfyui` and `model`.

```bash
ivry_cli init_app --project_name {project_name} --mode {comfyui/model}
```

### Examples:
- For **ComfyUI**:
  ```bash
  ivry_cli init_app --project_name my_project --mode comfyui
  ```
- For **Model-based projects**:
  ```bash
  ivry_cli init_app --project_name my_project --mode model
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
ivry_cli upload_app --model_name {project_name}
```
Or navigate to the project directory and execute:
```bash
cd {project_name}
ivry_cli upload_app
```

---

## Managing Your Models

### Check Uploaded Models
```bash
ivry_cli list_models
```

### List All Your Applications
View all your applications with detailed information:
```bash
ivry_cli list_apps
```
This displays ID, name, public status, state, and creation date for all your applications.

### Update an Existing Model
If you update `predict.py` after uploading, you can update your model:
```bash
ivry_cli update_app --model_id {model_id} --model_name {project_name}
```
Or use:
```bash
cd {project_name}
ivry_cli update_app --model_id {model_id}
```

---

## Hosting Your Project

### New: Unified Server Management

Start both the ivry_cli model server and cloudflared tunnel with a single command:

```bash
ivry_cli run_server [OPTIONS]
```

#### Options:
- `--project_path PATH`: Path to your project directory (default: current directory)
- `--detached`: Run with supervisor in daemon mode (requires supervisor package)
- `--background`: Run in background without supervisor
- `--force`: Override and restart even if services are already running

#### Examples:

```bash
# Start in foreground mode (blocks terminal)
cd my_project
ivry_cli run_server

# Start in background mode (frees terminal)
ivry_cli run_server --background

# Start in detached mode with supervisor (requires supervisor package)
ivry_cli run_server --detached

# Force restart if already running
ivry_cli run_server --force

# Specify a different project path
ivry_cli run_server --project_path /path/to/my_project --background
```

### Stopping the Server

```bash
# Stop services started with supervisor
ivry_cli stop_server [--project_path PATH]

# For background mode without supervisor, use
ivry_cli stop_server --background [--project_path PATH]
```

### Process Monitoring with Supervisor

If you've installed the supervisor package, you can use these commands:

```bash
# Check status of running services
ivry_cli supervisor_status [--project_path PATH]

# Control specific services
ivry_cli supervisor_control {start|stop|restart} [--process {all|ivry_server|cloudflared_tunnel}] [--project_path PATH]
```

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

## Pulling an Existing Project

You can pull an existing project from the ivry platform using the project ID:

```bash
ivry_cli pull_project --project_id {project_id} [--project_name {optional_local_name}] [--comfyui_port {port_number}]
```

This will:
1. Download the project configuration from the server
2. Create a local directory for the project
3. Create all necessary files (`predict.py`, `predict_signature.json`, etc.)
4. Set up CloudFlare tunnel configuration

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

## Additional Utilities

### Parse predict.py
Generate signature files from your predict.py:
```bash
ivry_cli parse_predict --predict_filename {path_to_predict.py}
```

### Upload Configuration
Upload configuration details to the server:
```bash
ivry_cli upload_config
```

### Get Heartbeat Status
Check the status of your application's heartbeat monitoring:
```bash
ivry_cli get_heartbeat_status
```

---

## Troubleshooting

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
- `logs/supervisord.log`: Supervisor logs (if using supervisor)

### Processes Won't Stop
If you're having trouble stopping processes:
```bash
# For supervisor-managed processes
ivry_cli stop_server --force

# For background processes
ps aux | grep ivry_cli
ps aux | grep cloudflared
# Then use the PIDs to terminate them
kill <PID>
```

---

## TODOs

- [ ] Support web pull
- [ ] WSL2 package
- [ ] Heartbeat sending improvements


### Completed Tasks:
✅ Background running mode  
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