# DEPLOYMENT.md｜部署計畫（MVP）

本文件描述在 Ubuntu VM 上使用 Docker Compose、GitHub Actions 與 systemd timer 的部署流程。

## 1. 基礎設置（一次性）

1. 建立 Ubuntu 22.04 VM（建議 4 vCPU / 8 GB RAM / 100 GB SSD）。
2. 安裝必要套件：
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
   sudo usermod -aG docker $USER
   ```
3. 於 `/srv/smart-investment` clone 專案：
   ```bash
   sudo mkdir -p /srv/smart-investment
   sudo chown $USER:$USER /srv/smart-investment
   git clone git@github.com:horstcheng/Smart-Investment-stretegy.git /srv/smart-investment
   ```
4. 建立 `.env`（使用 `.env.example` 內容）。

## 2. GitHub Actions → SSH 自動部署

- 建立 `infra/vm/deploy.sh`（範例內容）：
  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  cd /srv/smart-investment
  git fetch origin main
  git reset --hard origin/main
  make docker-up
  ```
- GitHub Actions workflow（摘要）：
  ```yaml
  name: Deploy to VM
  on:
    push:
      branches: [ "main" ]
  jobs:
    deploy:
      runs-on: ubuntu-latest
      steps:
        - name: Checkout
          uses: actions/checkout@v4
        - name: Deploy via SSH
          uses: appleboy/ssh-action@v1
          with:
            host: ${{ secrets.VM_HOST }}
            username: ${{ secrets.VM_USER }}
            key: ${{ secrets.VM_SSH_KEY }}
            script: |
              /srv/smart-investment/infra/vm/deploy.sh
  ```
- 所有 Secrets（`VM_HOST`, `VM_USER`, `VM_SSH_KEY`, `ANTHROPIC_API_KEY`, `POSTGRES_PASSWORD` 等）須儲存在 GitHub Secrets。

## 3. systemd timer 保底方案

- 建立 service：`/etc/systemd/system/radar-auto-update.service`
  ```ini
  [Unit]
  Description=Radar auto update service

  [Service]
  Type=oneshot
  ExecStart=/srv/smart-investment/infra/vm/deploy.sh --auto
  ```
- 建立 timer：`/etc/systemd/system/radar-auto-update.timer`
  ```ini
  [Unit]
  Description=Run radar deploy every 15 minutes

  [Timer]
  OnBootSec=5min
  OnUnitActiveSec=15min
  Unit=radar-auto-update.service

  [Install]
  WantedBy=timers.target
  ```
- 啟用：
  ```bash
  sudo systemctl daemon-reload
  sudo systemctl enable --now radar-auto-update.timer
  ```
- 功能：即使 GitHub Actions 失敗，timer 仍會定期拉取最新程式並執行 `deploy.sh`。

## 4. 手動部署

```bash
ssh vm-user@vm-host
cd /srv/smart-investment
make docker-down
make docker-up
```

## 5. 驗證步驟

1. `docker ps`：確認所有服務運行。
2. `curl http://localhost:8000/health`。
3. `curl http://localhost:8080`：檢查前端頁面。
4. `journalctl -u radar-auto-update.timer -n 20`：確認最近一次 timer 執行情況。

## 6. 回滾

1. 在 VM 上 `git checkout <previous-tag>`。
2. `make docker-up`。
3. 驗證 `/health` → 觀察 10 分鐘。
4. 記錄於 `CHANGELOG.md` 與 Issue。

## 7. 後續規劃

- 將部署腳本容器化（Ansible / Terraform）。
- 導入監控（Prometheus + Grafana 或 APM）。