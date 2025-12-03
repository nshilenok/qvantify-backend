# Manual Deployment Instructions for Digital Ocean

## Server Details
- **IPv4:** 164.92.177.11
- **IPv6:** 2a03:b0c0:3:f0:0:1:3d40:8000

## Step 1: Upload Backend Files

Upload the entire backend directory to `/srv/qvantify-backend/` on the server.

## Step 2: Upload Frontend Files

Upload the `web-build/` directory contents to `/srv/qvantify-frontend/` on the server.

## Step 3: Server Configuration

Run these commands on the server:

```bash
# Install dependencies
apt-get update
apt-get install -y python3-pip python3-venv nginx

# Setup backend
cd /srv/qvantify-backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install flask gunicorn psycopg2-binary openai

# Create systemd service
cat > /etc/systemd/system/qvantify-backend.service << 'EOF'
[Unit]
Description=Qvantify Backend API
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/srv/qvantify-backend
Environment="PATH=/srv/qvantify-backend/.venv/bin"
ExecStart=/srv/qvantify-backend/.venv/bin/gunicorn -w 2 -b 127.0.0.1:8001 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Configure Nginx
cat > /etc/nginx/sites-available/qvantify << 'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name _;

    ssl_certificate /etc/ssl/certs/nginx-selfsigned.crt;
    ssl_certificate_key /etc/ssl/private/nginx-selfsigned.key;

    client_max_body_size 20m;
    root /srv/qvantify-frontend;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8001/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
EOF

# Create SSL certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/ssl/private/nginx-selfsigned.key \
    -out /etc/ssl/certs/nginx-selfsigned.crt \
    -subj "/C=US/ST=State/L=City/O=Qvantify/CN=164.92.177.11"

# Enable and start services
ln -sf /etc/nginx/sites-available/qvantify /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

systemctl daemon-reload
systemctl enable qvantify-backend
systemctl start qvantify-backend
nginx -t && systemctl restart nginx

# Test deployment
echo "Testing backend:"
curl -s http://127.0.0.1:8001/project/ -H "projectId: ea762c3e-8dc1-4ec9-a33b-9581d6b69f77"

echo "Testing via nginx:"
curl -sk https://localhost/api/project/ -H "projectId: ea762c3e-8dc1-4ec9-a33b-9581d6b69f77"
```

## Step 4: Test Deployment

After running the configuration, test these URLs:

- **IPv4:** https://164.92.177.11
- **IPv6:** https://[2a03:b0c0:3:f0:0:1:3d40:8000]

## Files to Upload

### Backend Files (to `/srv/qvantify-backend/`):
- app.py
- database.py
- topic.py
- conversationInterface.py
- llmInterface.py
- credentials.py (with working Supabase config)
- All other .py files

### Frontend Files (to `/srv/qvantify-frontend/`):
- All contents from `web-build/` directory
- index.html
- static/ folder
- All assets
