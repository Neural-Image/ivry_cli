import os
import psutil
import socket
import platform

def find_comfyui_path_by_port(port=8188):
   """
   Find the installation path of ComfyUI by port number
   
   Parameters:
       port: Port number that ComfyUI is running on, default is 8188
       
   Returns:
       str: ComfyUI installation path, returns None if not found
   """
   # First check if the port is in use
   try:
       sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
       sock.settimeout(1)
       result = sock.connect_ex(('127.0.0.1', port))
       sock.close()
       
       if result != 0:
           print(f"Port {port} is not in use, ComfyUI may not be running")
           return None
   except Exception as e:
       print(f"Error checking port: {e}")
       return None
   
   # Find the process using that port
   for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'connections']):
       try:
           connections = proc.connections(kind='inet')
           for conn in connections:
               if conn.laddr.port == port:
                   print(f"Found port {port} on process PID={proc.pid}, name={proc.name()}")
                   
                   # Get the command line arguments of the process
                   cmdline = proc.cmdline()
                   if not cmdline:
                       continue
                   
                   # Check if it's a Python process
                   cmd_str = ' '.join(cmdline).lower()
                   if 'python' in cmd_str:
                       # Look for main.py or ComfyUI related scripts
                       for arg in cmdline:
                           if 'main.py' in arg or 'comfyui' in arg.lower():
                               # Found script path
                               script_path = os.path.abspath(arg)
                               install_path = os.path.dirname(script_path)
                               
                               # Verify if this is a ComfyUI directory
                               if os.path.exists(os.path.join(install_path, 'comfy')):
                                   print(f"Found ComfyUI path: {install_path}")
                                   return install_path
                       
                       # If no explicit path is found in the command line, use the process's working directory
                       try:
                           cwd = proc.cwd()
                           if os.path.exists(os.path.join(cwd, 'comfy')):
                               print(f"Found ComfyUI path based on working directory: {cwd}")
                               return cwd
                       except Exception as e:
                           print(f"Error getting working directory: {e}")
       except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
           continue
       except Exception as e:
           print(f"Error processing process: {e}")
   
   # If not found by port, try a broader search for ComfyUI processes
   print("No explicit ComfyUI process found by port, trying to find by name...")
   for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
       try:
           cmdline = proc.cmdline()
           if not cmdline:
               continue
           
           cmd_str = ' '.join(cmdline).lower()
           if 'comfyui' in cmd_str or ('main.py' in cmd_str and 'python' in cmd_str):
               for arg in cmdline:
                   if 'main.py' in arg:
                       script_path = os.path.abspath(arg)
                       install_path = os.path.dirname(script_path)
                       
                       if os.path.exists(os.path.join(install_path, 'comfy')):
                           print(f"Found ComfyUI path by process name: {install_path}")
                           return install_path
               
               # Use working directory as a fallback
               try:
                   cwd = proc.cwd()
                   if os.path.exists(os.path.join(cwd, 'comfy')):
                       print(f"Found ComfyUI path by process working directory: {cwd}")
                       return cwd
               except:
                   pass
       except:
           continue
   
   print("No running ComfyUI instance found")
   return None

# Usage example
if __name__ == "__main__":
   comfyui_path = find_comfyui_path_by_port(8188)
   if comfyui_path:
       print(f"ComfyUI is installed at: {comfyui_path}")
   else:
       print("Unable to determine ComfyUI path")