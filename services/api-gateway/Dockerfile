# API Gateway / Web BFF 的容器設定，僅包含最小依賴與健康檢查。
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY services/base-requirements.txt /tmp/base-requirements.txt
COPY services/api-gateway/requirements.txt /tmp/service-requirements.txt
RUN pip install --no-cache-dir -r /tmp/base-requirements.txt -r /tmp/service-requirements.txt

COPY services/api-gateway/app /app/app
COPY services/api-gateway/tests /app/tests

ENV PORT=8000
ENV SERVICE_NAME=api-gateway

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
