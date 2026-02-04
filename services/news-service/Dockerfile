# News Service 的容器設定。
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY services/base-requirements.txt /tmp/base-requirements.txt
COPY services/news-service/requirements.txt /tmp/service-requirements.txt
RUN pip install --no-cache-dir -r /tmp/base-requirements.txt -r /tmp/service-requirements.txt

COPY services/news-service/app /app/app
COPY services/news-service/tests /app/tests
COPY services/news-service/alembic.ini /app/alembic.ini
COPY services/news-service/alembic /app/alembic

ENV PORT=8003
ENV SERVICE_NAME=news-service

EXPOSE 8003

# 啟動時先執行資料庫遷移，再啟動服務
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
