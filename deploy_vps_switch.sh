# Deployment & Server Switch Execution Script for VPS (62.171.169.50)
# Run these commands via SSH on the VPS to point dmorales.site directly to DM AI OS and disable OptiCRM:

# 1. Stop OptiCRM / legacy Node/Next process if running on VPS
sudo systemctl stop opticrm 2>/dev/null || true
sudo systemctl disable opticrm 2>/dev/null || true
sudo pkill -f opticrm 2>/dev/null || true

# 2. Deploy Nginx Virtual Host configuration for dmorales.site
cat << 'EOF' | sudo tee /etc/nginx/sites-available/dmorales.site
server {
    listen 80;
    listen [::]:80;
    server_name dmorales.site www.dmorales.site 62.171.169.50;
    return 301 https://dmorales.site$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name www.dmorales.site;

    ssl_certificate /etc/letsencrypt/live/dmorales.site/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dmorales.site/privkey.pem;

    return 301 https://dmorales.site$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name dmorales.site 62.171.169.50;

    ssl_certificate /etc/letsencrypt/live/dmorales.site/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dmorales.site/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

# 3. Disable OptiCRM / default legacy sites from Nginx
sudo rm -f /etc/nginx/sites-enabled/default
sudo rm -f /etc/nginx/sites-enabled/*lafayette*
sudo rm -f /etc/nginx/sites-enabled/*opticrm*

# 4. Enable DM AI OS site
sudo ln -sf /etc/nginx/sites-available/dmorales.site /etc/nginx/sites-enabled/

# 5. Issue Let's Encrypt SSL certificate for dmorales.site
sudo certbot --nginx -d dmorales.site -d www.dmorales.site --non-interactive --agree-tos --email dmorales@dmorales.site 2>/dev/null || sudo certbot --nginx --reinstall -d dmorales.site -d www.dmorales.site --non-interactive

# 6. Restart Nginx service
sudo nginx -t && sudo systemctl restart nginx

# 7. Start DM AI OS backend service on port 8000
# Ensure Python 3 / uvicorn runs src.api.server
cd /opt/dm-ai-os 2>/dev/null || cd /root/dm-ai-os 2>/dev/null || true
nohup python3 -m src.api.server > /var/log/dm_ai_os.log 2>&1 &
