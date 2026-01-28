# Radar Service 的容器設定。
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY services/base-requirements.txt /tmp/base-requirements.txt
COPY services/radar-service/requirements.txt /tmp/service-requirements.txt
RUN pip install --no-cache-dir -r /tmp/base-requirements.txt -r /tmp/service-requirements.txt

COPY services/radar-service/app /app/app
COPY services/radar-service/tests /app/tests
COPY services/radar-service/alembic.ini /app/alembic.ini
COPY services/radar-service/alembic /app/alembic

ENV PORT=8002
ENV SERVICE_NAME=radar-service

EXPOSE 8002

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
