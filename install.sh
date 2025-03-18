#!/usr/bin/env bash

# Detect OS
OS=$(uname -s)

echo "🔍 Detected OS: $OS"

if [[ "$OS" == "Linux" ]]; then
    echo "📦 Updating system packages..."
    sudo apt update

    # Install Node.js (using NodeSource 18.x)
    echo "📦 Installing/Updating Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
    sudo apt install -y nodejs npm python3-pip

    # Ensure npm global packages do not require sudo
    mkdir -p ~/.npm-global
    npm config set prefix '~/.npm-global'
    echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
    source ~/.bashrc

    # Install Cloudflared
    echo "📦 Installing Cloudflared..."
    wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    sudo dpkg -i cloudflared-linux-amd64.deb

elif [[ "$OS" == "Darwin" ]]; then
    echo "🍏 Detected macOS system."

    # Install Homebrew if not installed
    if ! command -v brew &> /dev/null; then
        echo "📦 Homebrew not found. Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi

    # Update Homebrew
    echo "📦 Updating Homebrew..."
    brew update

    # Install Node.js and Python (if missing)
    if ! command -v node &> /dev/null; then
        echo "📦 Installing Node.js..."
        brew install node
    else
        echo "✅ Node.js is already installed: $(node -v)"
    fi

    if ! command -v pip3 &> /dev/null; then
        echo "📦 Installing Python3 and pip..."
        brew install python3
    fi

    # Install Cloudflared
    echo "📦 Installing Cloudflared..."
    brew install cloudflare/cloudflare/cloudflared

else
    echo "❌ Unsupported OS: $OS"
    exit 1
fi

# Ensure Node.js version >= 16
NODE_VERSION=$(node -v | cut -d. -f1 | cut -c2-)
if [[ $NODE_VERSION -lt 16 ]]; then
    echo "❌ Node.js version too low ($NODE_VERSION). Please update manually."
    exit 1
fi

# Install PM2 (for all systems)
if ! command -v pm2 &> /dev/null; then
    echo "📦 Installing PM2..."
    npm install -g pm2
    echo "✅ PM2 installed successfully: $(pm2 --version)"
else
    echo "✅ PM2 is already installed: $(pm2 --version)"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -e .

echo "✅ Installation completed."