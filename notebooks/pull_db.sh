#!/bin/bash
# Pulls a read-only snapshot of the live DB from the Pi for analysis in notebooks/.
# Mirrors push_pi.sh's direction (down instead of up). Re-run before analyzing to get fresh data.
set -e
PI="simonhans@raspberrypi"
REMOTE_DB="/mnt/serverdrive/coding/workouts/workouts.db"
LOCAL_DB="$(dirname "$0")/data/workouts_snapshot.db"

scp "$PI:$REMOTE_DB" "$LOCAL_DB"
echo "Snapshot saved to $LOCAL_DB"
