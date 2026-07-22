#!/usr/bin/env bash
# stop.sh — Остановка всех сервисов
set -euo pipefail

GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}Останавливаю все сервисы Crate...${NC}"
docker compose down

echo ""
echo "Если хотите удалить volumes (БД, Redis, MinIO):"
echo "  docker compose down -v"