# Locations communes du panel SPA + API (inclus depuis vzone.conf / vzone-ports.conf)
client_max_body_size 2048m;
client_body_timeout 3600s;

root /opt/vzone/frontend/dist;
index index.html;

location /assets/ {
    try_files $uri =404;
    expires 30d;
    add_header Cache-Control "public, immutable";
    access_log off;
}

location ^~ /api/v1/files/upload/ {
    proxy_pass http://vzone_asgi;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
    client_max_body_size 2048m;
    client_body_timeout 3600s;
    proxy_request_buffering off;
    proxy_buffering off;
    proxy_connect_timeout 60s;
    proxy_send_timeout 3600s;
    proxy_read_timeout 3600s;
}

location /api/ {
    proxy_pass http://vzone_asgi;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
    proxy_connect_timeout 60s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;
    proxy_next_upstream error timeout http_502 http_503;
}

location /ws/ {
    proxy_pass http://vzone_asgi;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400;
}

location /admin/ {
    proxy_pass http://vzone_asgi;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /static/ {
    alias /opt/vzone/backend/staticfiles/;
    expires 7d;
    access_log off;
}

include /etc/nginx/snippets/vzone-phpmyadmin.inc;

location / {
    try_files $uri $uri/ /index.html;
}

location = /index.html {
    add_header Cache-Control "no-store";
}
