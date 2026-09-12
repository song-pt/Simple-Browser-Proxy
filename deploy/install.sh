#!/bin/sh
set -eu
command -v docker >/dev/null 2>&1 || { echo '请先安装 Docker Engine 与 Compose 插件'; exit 1; }
docker compose version >/dev/null
docker compose up -d --build
docker compose ps
echo "部署完成：http://SERVER_IP:${PORT:-6789}/"
