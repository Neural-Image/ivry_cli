#!/usr/bin/env bash

# Detect OS
OS=$(uname -s)
echo "🔍 Detected OS: $OS"

if [[ "$OS" == "Linux" ]]; then
    echo "📦 Updating system packages..."
    sudo apt update

    if ! command -v curl &> /dev/null; then
        echo "📦 Installing curl..."
        sudo apt install -y curl
    fi

    export NVM_VERSION="v0.40.2"
    echo "📦 Installing NVM (Node Version Manager)..."
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh | bash

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

    # Install Node.js (using NVM)
    export NVM_VERSION="v0.40.2"
    echo "📦 Installing NVM (Node Version Manager)..."
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh | bash
else
    echo "❌ Unsupported OS: $OS"
    exit 1
fi

# === Configure NVM in profile file ===
if [[ $SHELL == */bash ]]; then
    PROFILE_FILE="$HOME/.bashrc"
elif [[ $SHELL == */zsh ]]; then
    PROFILE_FILE="$HOME/.zshrc"
else
    PROFILE_FILE="$HOME/.profile"
fi

# Ensure NVM is added to profile file
if ! grep -q 'export NVM_DIR' "$PROFILE_FILE"; then
    echo "📄 Adding NVM configuration to $PROFILE_FILE..."
    echo 'export NVM_DIR="$HOME/.nvm"' >> "$PROFILE_FILE"
    echo '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"' >> "$PROFILE_FILE"
    echo '[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"' >> "$PROFILE_FILE"
fi

# Load NVM for current session
export NVM_DIR="$([ -z "${XDG_CONFIG_HOME-}" ] && printf %s "${HOME}/.nvm" || printf %s "${XDG_CONFIG_HOME}/nvm")"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Ensure NVM is installed
if ! command -v nvm &> /dev/null; then
    echo "❌ NVM installation failed. Please install it manually."
    exit 1
fi

# Install and use the latest LTS version of Node.js
echo "📦 Installing latest LTS version of Node.js..."
nvm install --lts
nvm use --lts
nvm alias default node

# Install specific Node.js version (23)
echo "📦 Installing Node.js 23..."
nvm install 23
nvm use 23

# Ensure Node.js version >= 16
NODE_VERSION=$(node -v | cut -d. -f1 | cut -c2-)
if [[ $NODE_VERSION -lt 16 ]]; then
    echo "❌ Node.js version too low ($NODE_VERSION). Please update manually."
    exit 1
fi

# Update npm
echo "📦 Updating npm..."
npm install -g npm

# Install PM2
if ! command -v pm2 &> /dev/null; then
    echo "📦 Installing PM2..."
    npm install -g pm2
    echo "✅ PM2 installed successfully: $(pm2 --version)"
else
    echo "✅ PM2 is already installed: $(pm2 --version)"
fi

# Install Cloudflared (Linux)
if [[ "$OS" == "Linux" ]]; then
    echo "📦 Installing Cloudflared..."
    wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    sudo dpkg -i cloudflared-linux-amd64.deb
elif [[ "$OS" == "Darwin" ]]; then
    echo "📦 Installing Cloudflared..."
    brew install cloudflare/cloudflare/cloudflared
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -e .

echo "✅ Installation completed."

# Suggest reloading shell
echo "⚠️ Please run the following command to apply changes:"
echo "   source $PROFILE_FILE"
