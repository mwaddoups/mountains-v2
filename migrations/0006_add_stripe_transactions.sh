#!/bin/sh
# Adds a new stripe_transactions table to the DB
cp $1 $1.bak

QUERY="CREATE TABLE stripe_transactions (
    id TEXT PRIMARY KEY,
    dt_utc DATETIME NOT NULL,
    stripe_type TEXT NOT NULL,
    gross_p INTEGER NOT NULL,
    stripe_fee_p INTEGER NOT NULL,
    net_p INTEGER NOT NULL,
    payment_type TEXT,
    user_id INTEGER,
    event_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(event_id) REFERENCES events(id)
)"

uv run python -m sqlite3 $1 "$QUERY"