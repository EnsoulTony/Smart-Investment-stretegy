# DEPLOYMENT.md｜部署計畫（MVP）

本文件描述在 Ubuntu VM 上使用 Docker Compose、GitHub Actions 與 systemd timer 的部署流程。

## 1. 基礎設置（一次性）

1. 建立 Ubuntu 22.04 VM（建議 4 vCPU / 8 GB RAM / 100 GB SSD）。
2. 以 root 執行 bootstrap（會安裝 Docker、Compose plugin、Git，並建立 `/opt/radar-warroom`）：
  ```bash
  sudo bash /opt/radar-warroom/Smart-Investment-stretegy/infra/vm/bootstrap.sh
  ```
  如果是新機器，請先將 repo 放到 `/opt/radar-warroom/Smart-Investment-stretegy` 或改用下列方式：
  ```bash
  sudo mkdir -p /opt/radar-warroom
  sudo git clone https://github.com/EnsoulTony/Smart-Investment-stretegy.git /opt/radar-warroom/Smart-Investment-stretegy
  sudo bash /opt/radar-warroom/Smart-Investment-stretegy/infra/vm/bootstrap.sh
  ```
3. 首次執行後請登出再登入（套用 docker 群組權限）。
4. `.env` 會從 `.env.example` 建立，請填入必要機密資訊。

## 2. GitHub Actions → SSH 自動部署

- 部署腳本：`/opt/radar-warroom/Smart-Investment-stretegy/infra/vm/deploy.sh`
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
        - name: Setup SSH key
          run: |
            mkdir -p ~/.ssh
            printf '%s' "${{ secrets.VM_SSH_KEY }}" > ~/.ssh/id_rsa
            chmod 600 ~/.ssh/id_rsa
            ssh-keyscan -H "${{ secrets.VM_HOST }}" >> ~/.ssh/known_hosts
        - name: Deploy
          run: |
            set -o pipefail
            ssh -i ~/.ssh/id_rsa -p "${{ secrets.VM_SSH_PORT }}" "${{ secrets.VM_USER }}@${{ secrets.VM_HOST }}" "bash /opt/radar-warroom/Smart-Investment-stretegy/infra/vm/deploy.sh" | tee deploy.log
        - name: Deploy log summary (on failure)
          if: failure()
          run: |
            echo "==== deploy log (last 200 lines) ===="
            if [ -f deploy.log ]; then
              tail -n 200 deploy.log
            else
              echo "No deploy log captured."
            fi
  ```
- 需要在 GitHub Secrets 設定：
  - `VM_HOST`
  - `VM_USER`
  - `VM_SSH_KEY`
  - `VM_SSH_PORT`

## 3. systemd timer 保底方案

- 建立 service：`/etc/systemd/system/radar-deploy.service`
  ```ini
  [Unit]
  Description=Radar deploy service

  [Service]
  Type=oneshot
  WorkingDirectory=/opt/radar-warroom/Smart-Investment-stretegy
  ExecStart=/opt/radar-warroom/Smart-Investment-stretegy/infra/vm/deploy.sh --auto
  ```
- 建立 timer：`/etc/systemd/system/radar-deploy.timer`
  ```ini
  [Unit]
  Description=Run radar deploy every 15 minutes

  [Timer]
  OnBootSec=5min
  OnUnitActiveSec=15min
  Unit=radar-deploy.service

  [Install]
  WantedBy=timers.target
  ```
- 啟用：
  ```bash
  sudo systemctl daemon-reload
  sudo systemctl enable --now radar-deploy.timer
  ```
- 功能：即使 GitHub Actions 失敗，timer 仍會定期拉取最新程式並執行 `deploy.sh`。

## 4. 手動部署

```bash
ssh vm-user@vm-host
sudo /opt/radar-warroom/Smart-Investment-stretegy/infra/vm/deploy.sh
```

## 5. 驗證步驟

1. `docker ps`：確認所有服務運行。
2. `curl http://localhost:8000/health`。
3. `curl http://localhost:8080`：檢查前端頁面。
4. `journalctl -u radar-deploy.timer -n 20`：確認最近一次 timer 執行情況。

## 6. 回滾

1. 在 VM 上 `git checkout <previous-tag>`。
2. `make docker-up`。
3. 驗證 `/health` → 觀察 10 分鐘。
4. 記錄於 `CHANGELOG.md` 與 Issue。

## 7. 後續規劃

- 將部署腳本容器化（Ansible / Terraform）。
- 導入監控（Prometheus + Grafana 或 APM）。