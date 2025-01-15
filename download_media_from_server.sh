#!/bin/bash
set -x
set -e

rsync -av --delete -e ssh mountains:/var/www/html/media/uploads/profile/ src/mountains/static/profile/
rsync -av --delete -e ssh mountains:/var/www/html/media/uploads/photos/ src/mountains/static/uploads/photos/