# Deployment

On a base Ubuntu 24.04 droplet, we

1. Install nginx via apt.
2. Set a default config in `/etc/nginx/sites-enabled/mountains` for reverse proxy, and symlink
3. Follow the instructions from certbot to enable https, and set to renew in crontab.
4. Git clone our repo, and install uv.
5. Copy the test.db to prod.db, and the prod env to .env

TODO

- gunicorn installation
- building wheels
- automation
