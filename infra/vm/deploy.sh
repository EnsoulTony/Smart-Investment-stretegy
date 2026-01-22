#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/radar-warroom"
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
