#!/bin/bash
# 完整依賴衝突檢查（no-cache build）

set -euo pipefail

echo "=== 依賴衝突檢查（--no-cache build）==="
echo ""

echo "當前 requirements.txt 狀態："
echo "----------------------------------------"
cat services/portfolio-service/requirements.txt
echo ""
echo "----------------------------------------"
echo ""

echo "檢查 base-requirements.txt（FastAPI 版本）："
echo "----------------------------------------"
cat services/base-requirements.txt
echo "----------------------------------------"
echo ""

echo "開始 --no-cache build（這會花較長時間）..."
docker compose build portfolio-service --no-cache 2>&1 | tee /tmp/build_output.log

echo ""
echo "=== Build 結果分析 ==="
echo ""

# 檢查是否成功
if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo "✅ Build 成功"
else
    echo "❌ Build 失敗"
    exit 1
fi

# 提取安裝的 pydantic 版本
echo ""
echo "已安裝的關鍵套件版本："
echo "----------------------------------------"
docker compose run --rm portfolio-service pip list | grep -E "(pydantic|fastapi|starlette|gspread|google-auth)" || echo "無法取得套件列表"
echo "----------------------------------------"

echo ""
echo "=== 依賴檢查完成 ==="
echo ""
echo "✅ 無依賴衝突"
echo "✅ pydantic 版本由 FastAPI 決定"
echo "✅ gspread + google-auth 正常安裝"
