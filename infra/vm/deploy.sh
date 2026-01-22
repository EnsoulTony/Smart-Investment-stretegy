#!/usr/bin/env bash
#!/bin/bash
set -e  # 只要任何一個指令失敗，立即停止並回報錯誤
set -x  # 顯示執行的指令內容，方便除錯
set -euo pipefail

APP_DIR="/opt/radar-warroom/Smart-Investment-stretegy"
PREV_FILE="${APP_DIR}/.deploy_prev_commit"
HEALTH_URL="http://localhost:8000/health"

if [[ ! -d "${APP_DIR}/.git" ]]; then
	echo "Repo not found at ${APP_DIR}. Run infra/vm/bootstrap.sh first."
	exit 1
fi

cd "${APP_DIR}"

PREV_COMMIT=$(git rev-parse HEAD)
echo "${PREV_COMMIT}" > "${PREV_FILE}"

git fetch --all --prune
git reset --hard origin/main

# 新增這兩行來除錯
echo "=== Debug Info ==="
git remote -v           # 確認連的是哪個 Repo
git log -1 --oneline    # 確認重置後的最新 Commit 是哪一個
echo "=================="

# 停止並移除舊容器及 volumes，釋放佔用的端口
docker compose down -v --remove-orphans

docker compose build
docker compose up -d

for i in {1..20}; do
	if curl -fsS "${HEALTH_URL}" >/dev/null; then
		echo "Health check passed."
		exit 0
	fi
	sleep 6
done

echo "Health check failed. Rolling back."

if [[ -f "${PREV_FILE}" ]]; then
	ROLLBACK_COMMIT=$(cat "${PREV_FILE}")
	git reset --hard "${ROLLBACK_COMMIT}"
	docker compose up -d --build
	for i in {1..20}; do
		if curl -fsS "${HEALTH_URL}" >/dev/null; then
			echo "Rollback health check passed."
			exit 0
		fi
		sleep 6
	done
	echo "Rollback failed. Manual intervention required."
	exit 2
fi

echo "No rollback commit found. Manual intervention required."
exit 2
