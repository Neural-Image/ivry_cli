# Updated ivry_cli Documentation

## 🔥 Updates
- **2025/03/14**: Add log size limitation (1mb per file)
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

For Installation, please check our [ivry_cli documentation](https://neural-image.github.io/ivry_documentation/)

---

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
