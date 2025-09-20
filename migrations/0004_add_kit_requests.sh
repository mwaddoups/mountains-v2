#!/bin/sh
# Adds a new kit_item table to the DB
cp $1 $1.bak

QUERY="CREATE TABLE kit_requests (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    kit_id INTEGER REFERENCES kit_item(id) ON DELETE CASCADE ON UPDATE CASCADE,
    pickup_dt DATETIME NOT NULL,
    return_dt DATETIME NOT NULL,
    notes TEXT,
    is_approved BOOLEAN NOT NULL DEFAULT false,
    is_picked_up BOOLEAN NOT NULL DEFAULT false,
    is_returned BOOLEAN NOT NULL DEFAULT false,
    request_created_dt DATETIME DEFAULT current_timestamp
)"

uv run python -m sqlite3 $1 "$QUERY"
