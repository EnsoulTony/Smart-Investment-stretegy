# Research Service 的容器設定。
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY services/base-requirements.txt /tmp/base-requirements.txt
COPY services/research-service/requirements.txt /tmp/service-requirements.txt
RUN pip install --no-cache-dir -r /tmp/base-requirements.txt -r /tmp/service-requirements.txt

COPY services/research-service/app /app/app
COPY services/research-service/tests /app/tests

ENV PORT=8004
ENV SERVICE_NAME=research-service

EXPOSE 8004

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
