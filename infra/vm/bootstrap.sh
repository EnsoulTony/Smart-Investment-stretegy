#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/EnsoulTony/Smart-Investment-stretegy.git"
APP_DIR="/opt/radar-warroom"

if [[ $EUID -ne 0 ]]; then
	echo "Please run as root (sudo)."
	exit 1
fi

export DEBIAN_FRONTEND=noninteractive

apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release git

if ! command -v docker >/dev/null 2>&1; then
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
	chmod a+r /etc/apt/keyrings/docker.gpg
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
		> /etc/apt/sources.list.d/docker.list
	apt-get update -y
	apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

if ! getent group docker >/dev/null; then
	groupadd docker
fi

if [[ -n "${SUDO_USER:-}" ]]; then
	usermod -aG docker "${SUDO_USER}"
fi

mkdir -p "${APP_DIR}"
chown "${SUDO_USER:-root}":"${SUDO_USER:-root}" "${APP_DIR}"

if [[ ! -d "${APP_DIR}/.git" ]]; then
	git clone "${REPO_URL}" "${APP_DIR}"
fi

if [[ -f "${APP_DIR}/.env.example" && ! -f "${APP_DIR}/.env" ]]; then
	cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
fi

cd "${APP_DIR}"
docker compose up -d --build

echo "Bootstrap done. If this is the first run, log out and back in for docker group changes to take effect."
