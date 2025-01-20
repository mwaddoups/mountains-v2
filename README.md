# Deployment

On a base Ubuntu 24.04 droplet, we

1. Install nginx via apt. Set worker_processes to 1 in `/etc/nginx.conf`.
2. Set a default config in `/etc/nginx/sites-enabled/mountains` for reverse proxy, and symlink
3. Follow the instructions from certbot to enable https, and set to renew in crontab.

TODO

- gunicorn installation
- building wheels
- automation
