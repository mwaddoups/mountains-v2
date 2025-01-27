#!/bin/bash
set -x
set -e

ssh -t mountains "cd mountains/mountains && DJANGO_APP_STAGE=prod /root/.local/bin/poetry run python manage.py dumpdata -e contenttypes -e auth.Permission --indent 2 > datadump.json"
scp mountains:~/mountains/mountains/datadump.json datadump.json