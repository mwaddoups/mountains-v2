#!/bin/sh
# Adds a new tokens_ics table to the DB
cp $1 $1.bak

QUERY="CREATE TABLE tokens_ics (
    id TEXT PRIMARY KEY,
    user_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id)
)"

uv run python -m sqlite3 $1 "$QUERY"