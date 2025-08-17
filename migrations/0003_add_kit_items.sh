#!/bin/sh
# Adds a new kit_item table to the DB
cp $1 $1.bak

QUERY="CREATE TABLE kit_item (
    id INTEGER PRIMARY KEY,
    club_id TEXT NOT NULL,
    description TEXT NOT NULL,
    brand TEXT,
    color TEXT,
    size TEXT,
    kit_group INTEGER NOT NULL,
    kit_type TEXT,
    purchased_on DATE NOT NULL,
    purchase_price FLOAT NOT NULL
)"

uv run python -m sqlite3 $1 "$QUERY"
