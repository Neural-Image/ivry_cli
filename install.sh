#!/usr/bin/env bash
sudo apt update
pip install -e .
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb
echo "Installation completed."
