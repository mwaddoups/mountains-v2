#!/bin/bash

set -a
source prod.env
set +a

exec /root/.local/bin/uv run gunicorn --workers=3 --max-requests 1000 --max-requests-jitter 50 -k gthread --threads 2 -b 127.0.0.1:8000 'mountains:create_app()'