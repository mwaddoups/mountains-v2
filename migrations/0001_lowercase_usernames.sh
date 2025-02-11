#!/bin/sh
# Ensures all emails are lowercase, so comparisons when getting make sense
cp $1 $1.bak
uv run python -m sqlite3 $1 'UPDATE users SET email = LOWER(email);'
