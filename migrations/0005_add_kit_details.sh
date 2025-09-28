#!/bin/sh
# Adds a new kit_details table to the DB
cp $1 $1.bak

QUERY="CREATE TABLE kit_details (
    id INTEGER PRIMARY KEY,
    kit_id INTEGER REFERENCES kit_item(id) ON DELETE CASCADE ON UPDATE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL ON UPDATE CASCADE,
    added_dt DATETIME NOT NULL,
    condition TEXT,
    note TEXT,
    photo_path TEXT
)"

uv run python -m sqlite3 $1 "$QUERY"
