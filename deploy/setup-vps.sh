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
echo ""

# Prompt for domain and email
read -p "Enter your domain (e.g., ladx.ai): " DOMAIN
read -p "Enter your email for SSL certificates: " EMAIL

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
    echo "ERROR: Domain and email are required."
    exit 1
fi

echo ""
echo "Domain: $DOMAIN"
echo "Email:  $EMAIL"
echo ""

# Update system
echo "[1/9] Updating system packages..."
apt update && apt upgrade -y

# Install Python 3.11+ and essentials
echo "[2/9] Installing Python and dependencies..."
apt install -y python3 python3-pip python3-venv python3-dev \
    git nginx certbot python3-certbot-nginx \
    build-essential libffi-dev

# Create app user
echo "[3/9] Creating ladx user..."
if ! id "ladx" &>/dev/null; then
    useradd -m -s /bin/bash ladx
    echo "Created user 'ladx'"
else
    echo "User 'ladx' already exists"
fi

# Create app directory
echo "[4/9] Setting up app directory..."
mkdir -p /opt/ladx
chown ladx:ladx /opt/ladx

# Clone repo (run as ladx user)
echo "[5/9] Cloning repository..."
if [ -d "/opt/ladx/app" ]; then
    echo "App directory exists, pulling latest..."
    su - ladx -c "cd /opt/ladx/app && git pull origin main"
else
    su - ladx -c "cd /opt/ladx && git clone https://github.com/brijinchacko/Ladx.git app"
fi

# Setup Python virtual environment
echo "[6/9] Setting up Python environment..."
su - ladx -c "
cd /opt/ladx/app
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
"

# Create required directories
echo "[7/9] Creating data directories..."
su - ladx -c "
mkdir -p /opt/ladx/app/uploads
mkdir -p /opt/ladx/app/generated_docs
mkdir -p /opt/ladx/app/knowledge
mkdir -p /opt/ladx/app/output
"

# Configure Nginx
echo "[8/9] Configuring Nginx..."
# Substitute domain in nginx config
sed "s/ladx.ai/$DOMAIN/g" /opt/ladx/app/deploy/ladx-nginx.conf > /etc/nginx/sites-available/ladx

# For initial setup (before SSL), use HTTP-only config
cat > /etc/nginx/sites-available/ladx <<NGINX_CONF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    client_max_body_size 20M;

    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript image/svg+xml;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
    }

    location /static/ {
        alias /opt/ladx/app/web/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }
}
NGINX_CONF

ln -sf /etc/nginx/sites-available/ladx /etc/nginx/sites-enabled/ladx
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# Setup systemd service
echo "[9/9] Setting up systemd service..."
cp /opt/ladx/app/deploy/ladx.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable ladx

echo ""
echo "=========================================="
echo "  VPS Setup Complete!"
echo "=========================================="
echo ""
echo "IMPORTANT - Before starting the app:"
echo ""
echo "  1. Create .env file:"
echo "     sudo -u ladx nano /opt/ladx/app/.env"
echo ""
echo "     Required variables:"
echo "       OPENAI_API_KEY=sk-..."
echo "       SECRET_KEY=$(openssl rand -hex 32)"
echo "       DATABASE_URL=sqlite:///./ladx.db"
echo ""
echo "  2. Start the LADX service:"
echo "     sudo systemctl start ladx"
echo ""
echo "  3. Configure DNS in your Hostinger panel:"
echo "     - Log in to hpanel.hostinger.com"
echo "     - Go to Domains → $DOMAIN → DNS / Nameservers"
echo "     - Add/Edit an A record:"
echo "         Name: @       Points to: YOUR_VPS_IP"
echo "         Name: www     Points to: YOUR_VPS_IP"
echo "     - Wait 5-15 minutes for DNS propagation"
echo ""
echo "  4. After DNS propagates, get SSL certificate:"
echo "     sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN --email $EMAIL --agree-tos --non-interactive"
echo ""
echo "  5. After SSL is configured, replace nginx config with full SSL version:"
echo "     sudo sed 's/ladx.ai/$DOMAIN/g' /opt/ladx/app/deploy/ladx-nginx.conf > /etc/nginx/sites-available/ladx"
echo "     sudo nginx -t && sudo systemctl restart nginx"
echo ""
echo "  6. Verify the app is running:"
echo "     curl https://$DOMAIN/health"
echo ""
echo "  7. (Optional) Setup auto-renewal for SSL:"
echo "     sudo certbot renew --dry-run"
echo ""
