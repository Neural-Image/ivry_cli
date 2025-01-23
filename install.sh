#!/usr/bin/env bash

# 1. Update package list
sudo apt update

# 2. Install Python pip and venv  packages
sudo apt install -y python3-pip python3-venv

# 3. Create and activate a new virtual environment named "myenv"
python3 -m venv myenv
source myenv/bin/activate

# 4. Install current directory as an editable package and install gradio
pip install -e .
pip install gradio
pip uninstall websockets
pip install websocket-client
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb
echo "Installation completed."
