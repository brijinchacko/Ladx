#!/bin/bash
# ===========================================
# LADX - Quick Update Script
# ===========================================
# Run: sudo bash /opt/ladx/app/deploy/update.sh
# ===========================================

set -e

echo "Pulling latest code..."
su - ladx -c "cd /opt/ladx/app && git pull origin main"

echo "Updating dependencies..."
su - ladx -c "cd /opt/ladx/app && source venv/bin/activate && pip install -r requirements.txt"

echo "Restarting LADX service..."
systemctl restart ladx

echo "Checking status..."
sleep 2
systemctl status ladx --no-pager

echo ""
echo "Update complete! Site: https://ladx.ai"
