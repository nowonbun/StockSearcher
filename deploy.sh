#!/usr/bin/env bash
set -e

echo ">> docker compose down (ignore errors)"
docker compose down || true

echo ">> git pull origin"
git pull origin

echo ">> docker compose build"
docker compose build

echo ">> docker compose up -d"
docker compose up -d

echo ">> done"
