# Sprint 1-4.B: Valuation Service（估值層）
# 鐵律：禁止任何 DB driver，只能透過 HTTP 從 portfolio-service 取數

FROM python:3.12-slim

WORKDIR /app

# 複製 base requirements（共用依賴）
COPY services/base-requirements.txt /app/services/base-requirements.txt
# 複製 service 專屬依賴
COPY services/valuation-service/requirements.txt /app/services/valuation-service/requirements.txt

# 安裝依賴
RUN pip install --no-cache-dir \
    -r /app/services/base-requirements.txt \
    -r /app/services/valuation-service/requirements.txt

# 複製 service code
COPY services/valuation-service/app /app/app

# 複製測試
COPY services/valuation-service/tests /app/tests

# 暴露端口
EXPOSE 8005

# 啟動 uvicorn
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8005}"]
