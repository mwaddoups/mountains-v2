#!/bin/bash

set -a
source prod.env
set +a

exec /root/.local/bin/uv run gunicorn --workers=4 --max-requests 100 --max-requests-jitter 10 -k gthread --threads 4 -b 127.0.0.1:8000 'mountains:create_app()'