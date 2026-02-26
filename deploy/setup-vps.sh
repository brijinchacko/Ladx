#!/bin/bash
# ===========================================
# LADX VPS Setup Script - Ubuntu 22/24 LTS
# ===========================================
# Run as root: sudo bash setup-vps.sh
# ===========================================

set -e

echo "=========================================="
echo "  LADX - VPS Server Setup"
echo "=========================================="

# Update system
echo "[1/7] Updating system packages..."
apt update && apt upgrade -y

# Install Python 3.11+ and essentials
echo "[2/7] Installing Python and dependencies..."
apt install -y python3 python3-pip python3-venv python3-dev \
    git nginx certbot python3-certbot-nginx \
    build-essential libffi-dev

# Create app user
echo "[3/7] Creating ladx user..."
if ! id "ladx" &>/dev/null; then
    useradd -m -s /bin/bash ladx
    echo "Created user 'ladx'"
else
    echo "User 'ladx' already exists"
fi

# Create app directory
echo "[4/7] Setting up app directory..."
mkdir -p /opt/ladx
chown ladx:ladx /opt/ladx

# Clone repo (run as ladx user)
echo "[5/7] Cloning repository..."
if [ -d "/opt/ladx/app" ]; then
    echo "App directory exists, pulling latest..."
    su - ladx -c "cd /opt/ladx/app && git pull origin main"
else
    su - ladx -c "cd /opt/ladx && git clone https://github.com/brijinchacko/Ladx.git app"
fi

# Setup Python virtual environment
echo "[6/7] Setting up Python environment..."
su - ladx -c "
cd /opt/ladx/app
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
"

# Create required directories
echo "[7/7] Creating data directories..."
su - ladx -c "
mkdir -p /opt/ladx/app/uploads
mkdir -p /opt/ladx/app/generated_docs
mkdir -p /opt/ladx/app/knowledge
mkdir -p /opt/ladx/app/output
"

echo ""
echo "=========================================="
echo "  VPS Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Create .env file:  sudo -u ladx nano /opt/ladx/app/.env"
echo "  2. Copy nginx config: sudo cp /opt/ladx/app/deploy/ladx-nginx.conf /etc/nginx/sites-available/ladx"
echo "  3. Enable site:       sudo ln -sf /etc/nginx/sites-available/ladx /etc/nginx/sites-enabled/ladx"
echo "  4. Remove default:    sudo rm -f /etc/nginx/sites-enabled/default"
echo "  5. Test nginx:        sudo nginx -t"
echo "  6. Copy systemd:      sudo cp /opt/ladx/app/deploy/ladx.service /etc/systemd/system/"
echo "  7. Start service:     sudo systemctl enable --now ladx"
echo "  8. Restart nginx:     sudo systemctl restart nginx"
echo "  9. Get SSL cert:      sudo certbot --nginx -d ladx.ai -d www.ladx.ai"
echo ""
