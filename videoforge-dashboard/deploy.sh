#!/bin/bash
set -e
APP_DIR="/opt/videoforge"
REPO="https://github.com/ethinxsolutionsau-prog/video-forge-449.git"

echo "=== VideoForge Optimizer Deploy ==="
sudo apt-get update -qq && sudo apt-get install -y -qq ffmpeg python3-venv python3-pip nginx git curl

if [ -d "$APP_DIR/.git" ]; then cd $APP_DIR && git pull; else sudo rm -rf $APP_DIR && sudo git clone $REPO $APP_DIR && sudo chown -R $(whoami) $APP_DIR; fi

cd $APP_DIR/videoforge-dashboard
python3 -m venv venv --clear && source venv/bin/activate
pip install --quiet fastapi uvicorn python-multipart websockets aiofiles pydantic
mkdir -p /tmp/videoforge/{uploads,processing,processed}

sudo tee /etc/nginx/sites-available/videoforge > /dev/null << 'NGINX'
server {
    listen 80;
    server_name _;
    client_max_body_size 500M;
    location / { root /opt/videoforge/videoforge-dashboard/frontend/dist; try_files $uri $uri/ /index.html; }
    location /api/ { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; proxy_read_timeout 600s; }
    location /ws/ { proxy_pass http://127.0.0.1:8000; proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; proxy_read_timeout 600s; }
}
NGINX

sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/videoforge /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo tee /etc/systemd/system/videoforge.service > /dev/null << 'SYSTEMD'
[Unit]
Description=VideoForge Optimizer
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory=/opt/videoforge/videoforge-dashboard
Environment=PYTHONPATH=/opt/videoforge/videoforge-dashboard
ExecStart=/opt/videoforge/videoforge-dashboard/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always
[Install]
WantedBy=multi-user.target
SYSTEMD

sudo systemctl daemon-reload && sudo systemctl enable videoforge && sudo systemctl restart videoforge
sleep 2 && curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool 2>/dev/null || true
echo ""
echo "=== DEPLOYED ==="
echo "Dashboard: http://$(curl -s ifconfig.io 2>/dev/null || echo YOUR_IP)/"
echo "Logs: sudo journalctl -u videoforge -f"
