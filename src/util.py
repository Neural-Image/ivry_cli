import yaml
from pathlib import Path
import json
import psutil, os, sys, subprocess

IVRY_CREDENTIAL_DIR = Path.home() / ".ivry"


def get_apikey():
        token_path = IVRY_CREDENTIAL_DIR / "token.txt"
        if token_path.exists():
            with open(IVRY_CREDENTIAL_DIR / "token.txt", "r", encoding="utf-8") as f:
                return f.read()
        else:
            raise Exception("Sorry, you need to login with your apikey first. You can get your apikey from our website:https://test-pc.neuralimage.net after you login and become a creator!")
            
            

def find_comfyui_processes():
    """查找 ComfyUI 主进程（排除子进程）"""
    current_pid = os.getpid()  # 获取当前脚本的 PID

    for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline', 'cwd']):
        try:
            pid = proc.pid
            name = (proc.info['name'] or "").lower()
            exe = (proc.info['exe'] or "").lower() if proc.info.get('exe') else ""
            cmdline = " ".join(proc.info['cmdline']).lower() if proc.info.get('cmdline') else ""
            cwd = (proc.info.get('cwd') or "").lower() if proc.info.get('cwd') else ""

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

        # **排除自身**
        if pid == current_pid:
            continue

        # **只选择主进程**
        if ("comfyui" in cmdline or "comfyui" in exe or "comfyui" in cwd):
            if "main.py" in cmdline:  # 只匹配 main.py 进程，防止匹配到子进程
                return proc  # 直接返回第一个匹配的进程

    return None  # 没找到

def get_comfyui_install_path(proc):
    """获取 ComfyUI 进程的安装路径"""
    try:
        cmdline = proc.cmdline()
    except psutil.AccessDenied:
        cmdline = proc.info.get('cmdline') or []

    for arg in cmdline:
        if "comfyui" in arg.lower():
            if os.path.isfile(arg):
                return os.path.dirname(arg)

    try:
        cwd = proc.cwd()
    except psutil.AccessDenied:
        cwd = proc.info.get('cwd') or ""

    if cwd and "comfyui" in cwd.lower():
        return cwd

    return None  # 无法确定路径

def get_comfyui_ports(proc):
    """获取 ComfyUI 监听的端口"""
    try:
        # **尝试从主进程获取端口**
        for conn in proc.connections(kind='inet'):
            if conn.status == psutil.CONN_LISTEN:
                return conn.laddr.port  # 直接返回监听的端口

    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass  # 权限不足，跳过

    # **如果主进程没有监听端口，检查所有进程**
    for p in psutil.process_iter(['pid', 'name', 'connections']):
        try:
            for conn in p.connections(kind='inet'):
                if conn.status == psutil.CONN_LISTEN and conn.laddr.port in [8188, 8000]:  # ComfyUI 常用端口
                    return conn.laddr.port
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

    return None  # 没找到端口