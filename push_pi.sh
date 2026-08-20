#!/bin/bash
set -e
PI="simonhans@raspberrypi"
REMOTE="/mnt/serverdrive/coding/workouts"

rsync -av --exclude='*.db' --exclude='__pycache__' --exclude='.git' --exclude='venv' \
  /home/simonhans/coding/workouts/ "$PI:$REMOTE/"

ssh "$PI" "sudo systemctl restart workouts && sudo systemctl status workouts --no-pager"
