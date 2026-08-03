# Snippet Nginx — phpMyAdmin (inclus depuis vzone.conf)
location /phpmyadmin {
    alias __PMA_ROOT__/;
    index index.php;
    location ~ ^/phpmyadmin/(.+\.php)$ {
        alias __PMA_ROOT__/$1;
        include fastcgi_params;
        fastcgi_param SCRIPT_FILENAME __PMA_ROOT__/$1;
        fastcgi_pass unix:__PHP_SOCK__;
        fastcgi_read_timeout 300;
    }
    location ~* ^/phpmyadmin/(.+\.(jpg|jpeg|gif|css|png|js|ico|html|xml|txt))$ {
        alias __PMA_ROOT__/$1;
        expires 7d;
        access_log off;
    }
}
