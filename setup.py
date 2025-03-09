from setuptools import setup, find_packages
from setuptools.command.install import install
from setuptools.command.develop import develop
import os
import platform
import subprocess
import sys

def check_and_install_nodejs_deps():
    """Check and install Node.js dependencies (npm and PM2)"""
    system = platform.system().lower()
    print("Checking Node.js dependencies...")
    
    # Check if Node.js is installed
    try:
        node_result = subprocess.run(
            ["node", "--version"], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        
        if node_result.returncode == 0:
            print(f"✅ Node.js is installed: {node_result.stdout.strip()}")
        else:
            print("❌ Node.js is not installed. Please install Node.js and npm manually.")
            print("   Linux: sudo apt install nodejs npm")
            print("   macOS: brew install node")
            print("   Windows: visit https://nodejs.org/")
            return False
    except FileNotFoundError:
        print("❌ Node.js is not installed. Please install Node.js and npm manually.")
        print("   Linux: sudo apt install nodejs npm")
        print("   macOS: brew install node")
        print("   Windows: visit https://nodejs.org/")
        return False
    
    # Check if npm is installed
    try:
        npm_result = subprocess.run(
            ["npm", "--version"], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        
        if npm_result.returncode == 0:
            print(f"✅ npm is installed: {npm_result.stdout.strip()}")
        else:
            print("❌ npm is not installed. Please install npm manually.")
            return False
    except FileNotFoundError:
        print("❌ npm is not installed. Please install npm manually.")
        return False
    
    # Check if PM2 is installed, install it if not
    try:
        pm2_result = subprocess.run(
            ["pm2", "--version"], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        
        if pm2_result.returncode == 0:
            print(f"✅ PM2 is installed: {pm2_result.stdout.strip()}")
        else:
            print("📦 Installing PM2...")
            install_result = subprocess.run(
                ["npm", "install", "-g", "pm2"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            
            if install_result.returncode == 0:
                print("✅ PM2 installed successfully")
            else:
                print(f"❌ PM2 installation failed: {install_result.stderr}")
                return False
    except FileNotFoundError:
        print("📦 Installing PM2...")
        try:
            install_result = subprocess.run(
                ["npm", "install", "-g", "pm2"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            
            if install_result.returncode == 0:
                print("✅ PM2 installed successfully")
            else:
                print(f"❌ PM2 installation failed: {install_result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Error installing PM2: {str(e)}")
            return False
    
    return True

class PostInstallCommand(install):
    """Post-installation command: install Node.js dependencies"""
    def run(self):
        install.run(self)
        check_and_install_nodejs_deps()
        
class PostDevelopCommand(develop):
    """Development mode post-installation command: install Node.js dependencies"""
    def run(self):
        develop.run(self)
        check_and_install_nodejs_deps()

# Setup configuration
setup(
    cmdclass={
        'install': PostInstallCommand,
        'develop': PostDevelopCommand,
    },
    # Other configuration will be loaded from pyproject.toml
)