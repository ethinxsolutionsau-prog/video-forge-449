#!/bin/bash
# VideoForge Optimizer — Full Deployment Script
# Run on Hetzner server: cd /opt && sudo bash deploy.sh

set -e
APP_DIR="/opt/videoforge"
REPO_URL="https://github.com/ethinxsolutionsau-prog/video-forge-449.git"
BACKEND_PORT=8000

echo "=========================================="
echo "  VideoForge Optimizer — Deploy"
echo "=========================================="

# 0. Install Node.js 20 if needed
if ! command -v node &> /dev/null || [ "$(node -v | cut -d'v' -f2 | cut -d'.' -f1)" != "20" ]; then
    echo "[0/8] Installing Node.js 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
    sudo apt-get install -y -qq nodejs
fi
echo "Node: $(node -v), NPM: $(npm -v)"

# 1. System dependencies
echo "[1/8] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq ffmpeg python3-venv python3-pip nginx git
ffmpeg -version | head -1

# 2. Clone/update repo
echo "[2/8] Cloning/updating repository..."
if [ -d "$APP_DIR/.git" ]; then
    cd $APP_DIR && git reset --hard HEAD && git pull origin main
else
    sudo rm -rf $APP_DIR
    sudo git clone $REPO_URL $APP_DIR
    sudo chown -R $(whoami):$(whoami) $APP_DIR
fi

# 3. Build frontend
echo "[3/8] Building frontend..."
cd $APP_DIR/videoforge-dashboard
if [ -d "$APP_DIR/videoforge-dashboard/frontend" ]; then
    echo "Using pre-built frontend"
else
    if [ -d "$APP_DIR/videoforge-dashboard/src" ]; then
        if [ ! -d "node_modules" ]; then
            npm install 2>/dev/null || echo "npm install skipped"
        fi
        npm run build 2>/dev/null || echo "Build skipped"
        [ -d "dist" ] && mv dist frontend
    fi
fi
mkdir -p frontend

# 4. Setup Python backend
echo "[4/8] Setting up Python backend..."
cd $APP_DIR/videoforge-dashboard
python3 -m venv venv --clear
source venv/bin/activate
pip install --quiet fastapi uvicorn[standard] python-multipart websockets aiofiles pydantic

# 5. Temp directories
mkdir -p /tmp/videoforge/{uploads,processing,processed}

# 6. Nginx config
echo "[5/8] Configuring nginx..."
sudo tee /etc/nginx/sites-available/videoforge > /dev/null << 'NGINX'
server {
    listen 80;
    server_name _;
    client_max_body_size 500M;

    location / {
        root /opt/videoforge/videoforge-dashboard/frontend;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 600s;
    }
}
NGINX

sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/videoforge /etc/nginx/sites-enabled/videoforge
sudo nginx -t && sudo systemctl reload nginx

# 7. Systemd service
echo "[6/8] Creating systemd service..."
sudo tee /etc/systemd/system/videoforge.service > /dev/null << 'SYSTEMD'
[Unit]
Description=VideoForge Optimizer Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/videoforge/videoforge-dashboard
Environment=PYTHONPATH=/opt/videoforge/videoforge-dashboard
ExecStart=/opt/videoforge/videoforge-dashboard/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SYSTEMD

sudo systemctl daemon-reload
sudo systemctl enable videoforge
sudo systemctl restart videoforge

# 8. Verify
echo "[7/8] Waiting for backend..."
sleep 3
HEALTH=$(curl -s http://127.0.0.1:8000/api/health 2>/dev/null || echo '{}')
echo "Health: $HEALTH"

echo ""
echo "=========================================="
echo "  DEPLOYMENT COMPLETE"
echo "=========================================="
IP=$(curl -s ifconfig.io 2>/dev/null || echo 'YOUR_SERVER_IP')
echo "Dashboard: http://$IP/"
echo "API:       http://$IP/api/health"
echo ""
echo "Logs:  sudo journalctl -u videoforge -f"
echo "=========================================="
