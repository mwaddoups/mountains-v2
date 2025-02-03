#!/bin/bash
set -x
set -e

cp test.db test.db.bak
scp mountains2:/var/www/mountains-v2/prod.db test.db