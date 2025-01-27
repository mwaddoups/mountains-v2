#!/bin/bash

set -a
source prod.env
set +a

uv run gunicorn --workers=4 -k gthread --threads 4 -b /tmp/gunicorn.sock 'mountains:create_app()'