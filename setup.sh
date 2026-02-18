#!/bin/bash

# MF-Balancer Robust Setup Script
# Colors for better output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo "🚀 Starting MF-Balancer setup..."

# 1. Check Python installation
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed. Please install Python 3.${NC}"
    exit 1
fi

# 2. Check if venv exists, if not create it
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment (.venv)..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to create virtual environment.${NC}"
        exit 1
    fi
fi

# 3. Upgrade pip and install dependencies
echo "🛠️  Updating pip and installing dependencies..."
.venv/bin/pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    .venv/bin/pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to install dependencies.${NC}"
        exit 1
    fi
else
    echo -e "${RED}Error: requirements.txt not found.${NC}"
    exit 1
fi

# 4. Create necessary directory structure if missing
echo "📂 Ensuring directory structure exists..."
mkdir -p mf_balancer/data mf_balancer/output
touch mf_balancer/data/.gitkeep mf_balancer/output/.gitkeep

# 5. Handle .env file
if [ ! -f ".env" ]; then
    echo "📝 Creating initial .env template..."
    cat <<EOT >> .env
# Kite Connect Credentials
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here

# Access Token (Will be auto-populated after login)
# KITE_ACCESS_TOKEN=
EOT
    echo -e "${GREEN}Created .env file. Please add your credentials.${NC}"
else
    echo "✅ .env file already exists."
fi

# 6. Make scripts executable
chmod +x setup.sh run.sh

echo -e "\n${GREEN}✨ Setup complete!${NC}"
echo "1. Edit the .env file with your Zerodha API keys."
echo "2. Run './run.sh' to start the tool."
