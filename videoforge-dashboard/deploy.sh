#!/bin/bash
# VideoForge Optimizer — Deployment Script
# Run on Hetzner server: bash deploy.sh

set -e
APP_DIR="/opt/videoforge"
REPO_URL="https://github.com/ethinxsolutionsau-prog/video-forge-449.git"
NGINX_CONF="/etc/nginx/sites-enabled/videoforge"

echo "=== VideoForge Optimizer Deployment ==="

# 1. System dependencies
echo "[1/7] Installing dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq ffmpeg python3-venv python3-pip nginx git
ffmpeg -version | head -1

# 2. Clone/pull repo
echo "[2/7] Cloning repository..."
if [ -d "$APP_DIR/.git" ]; then
    cd $APP_DIR && git pull origin main
else
    sudo rm -rf $APP_DIR
    sudo git clone $REPO_URL $APP_DIR
    sudo chown -R $(whoami) $APP_DIR
fi

# 3. Setup Python environment
echo "[3/7] Setting up Python virtual environment..."
cd $APP_DIR/videoforge-dashboard
python3 -m venv venv --clear
source venv/bin/activate
pip install --quiet fastapi uvicorn[standard] python-multipart websockets aiofiles pydantic

# 4. Create temp directories
mkdir -p /tmp/videoforge/{uploads,processing,processed}

# 5. Nginx config
echo "[4/7] Configuring nginx..."
sudo tee /etc/nginx/sites-available/videoforge > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;
    client_max_body_size 500M;

    # Frontend static files
    location / {
        root /opt/videoforge/videoforge-dashboard/frontend;
        try_files $uri $uri/ /index.html;
    }

    # Backend API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }

    # WebSocket proxy
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 600s;
    }
}
EOF

sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/videoforge /etc/nginx/sites-enabled/videoforge
sudo nginx -t && sudo systemctl reload nginx

# 6. Systemd service
echo "[5/7] Creating systemd service..."
sudo tee /etc/systemd/system/videoforge.service > /dev/null << 'EOF'
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
EOF

sudo systemctl daemon-reload
sudo systemctl enable videoforge
sudo systemctl restart videoforge

# 7. Verify
echo "[6/7] Verifying..."
sleep 2
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool 2>/dev/null || echo "Health check failed"

echo ""
echo "=== Deployment Complete ==="
echo "Frontend: http://$(curl -s ifconfig.me)/"
echo "API:      http://$(curl -s ifconfig.me)/api/health"
echo "Backend:  http://127.0.0.1:8000/api/health"
echo ""
echo "Status:   sudo systemctl status videoforge"
echo "Logs:     sudo journalctl -u videoforge -f"
echo "Nginx:    sudo nginx -t && sudo systemctl status nginx"
