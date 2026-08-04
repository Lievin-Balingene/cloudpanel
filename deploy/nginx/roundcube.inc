# Snippet Nginx — Roundcube Webmail (inclus depuis vzone.conf)
location = /webmail {
    return 302 /webmail/;
}
location /webmail/ {
    alias __RC_ROOT__/;
    index index.php;

    # PHP : SCRIPT_FILENAME absolu + QUERY_STRING explicite
    # (alias+regex perd parfois ?t=… → « Token invalide »)
    location ~ ^/webmail/(.+\.php)(/.*)?$ {
        include fastcgi_params;
        fastcgi_param SCRIPT_FILENAME __RC_ROOT__/$1;
        fastcgi_param SCRIPT_NAME /webmail/$1;
        fastcgi_param PATH_INFO $2;
        fastcgi_param QUERY_STRING $query_string;
        fastcgi_param REQUEST_URI $request_uri;
        fastcgi_pass unix:__PHP_SOCK__;
        fastcgi_read_timeout 300;
    }

    location ~* ^/webmail/(.+\.(jpg|jpeg|gif|css|png|js|ico|html|xml|txt|woff2?|ttf|svg))$ {
        alias __RC_ROOT__/$1;
        expires 7d;
        access_log off;
    }
}
