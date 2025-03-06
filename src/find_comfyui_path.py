import os
import psutil
import socket
import platform

def find_comfyui_path_by_port(port=8188):
    """
    通过端口号查找 ComfyUI 的安装路径
    
    参数:
        port: ComfyUI 运行的端口号，默认为 8188
        
    返回:
        str: ComfyUI 的安装路径，如果未找到则返回 None
    """
    # 首先检查端口是否正在使用
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        
        if result != 0:
            print(f"端口 {port} 未被使用，ComfyUI 可能未运行")
            return None
    except Exception as e:
        print(f"检查端口时出错: {e}")
        return None
    
    # 查找使用该端口的进程
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'connections']):
        try:
            connections = proc.connections(kind='inet')
            for conn in connections:
                if conn.laddr.port == port:
                    print(f"在进程 PID={proc.pid}, 名称={proc.name()} 上找到端口 {port}")
                    
                    # 获取进程的命令行参数
                    cmdline = proc.cmdline()
                    if not cmdline:
                        continue
                    
                    # 检查是否是 Python 进程
                    cmd_str = ' '.join(cmdline).lower()
                    if 'python' in cmd_str:
                        # 查找 main.py 或 ComfyUI 相关的脚本
                        for arg in cmdline:
                            if 'main.py' in arg or 'comfyui' in arg.lower():
                                # 找到脚本路径
                                script_path = os.path.abspath(arg)
                                install_path = os.path.dirname(script_path)
                                
                                # 验证这是否是 ComfyUI 目录
                                if os.path.exists(os.path.join(install_path, 'comfy')):
                                    print(f"找到 ComfyUI 路径: {install_path}")
                                    return install_path
                        
                        # 如果没有在命令行找到明确的路径，使用进程的工作目录
                        try:
                            cwd = proc.cwd()
                            if os.path.exists(os.path.join(cwd, 'comfy')):
                                print(f"基于工作目录找到 ComfyUI 路径: {cwd}")
                                return cwd
                        except Exception as e:
                            print(f"获取工作目录时出错: {e}")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            continue
        except Exception as e:
            print(f"处理进程时出错: {e}")
    
    # 如果通过端口未找到，尝试更广泛地搜索 ComfyUI 进程
    print("通过端口未找到明确的 ComfyUI 进程，尝试通过名称查找...")
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
                            print(f"通过进程名找到 ComfyUI 路径: {install_path}")
                            return install_path
                
                # 使用工作目录作为备选
                try:
                    cwd = proc.cwd()
                    if os.path.exists(os.path.join(cwd, 'comfy')):
                        print(f"通过进程工作目录找到 ComfyUI 路径: {cwd}")
                        return cwd
                except:
                    pass
        except:
            continue
    
    print("未找到运行中的 ComfyUI 实例")
    return None

# 使用示例
if __name__ == "__main__":
    comfyui_path = find_comfyui_path_by_port(8188)
    if comfyui_path:
        print(f"ComfyUI 安装在: {comfyui_path}")
    else:
        print("无法确定 ComfyUI 路径")