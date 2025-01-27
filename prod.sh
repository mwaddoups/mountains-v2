#!/bin/bash

set -a
source prod.env
set +a

uv run gunicorn --workers=4 -k gthread --threads 4 -b ['127.0.0.1:8000'] 'mountains:create_app()'