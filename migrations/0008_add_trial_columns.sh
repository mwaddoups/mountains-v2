#!/bin/sh
# Ensures all emails are lowercase, so comparisons when getting make sense
cp $1 $1.bak
uv run python -m sqlite3 $1 'ALTER TABLE users ADD COLUMN trial_start_date DATE;'
uv run python -m sqlite3 $1 'ALTER TABLE users ADD COLUMN finished_trial BOOLEAN NOT NULL DEFAULT false;'
