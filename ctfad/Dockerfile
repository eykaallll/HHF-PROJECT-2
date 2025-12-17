FROM python:3.11-slim

ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Jakarta \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential tzdata \
    && ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo "${TZ}" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY helpfulhelper.py .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

VOLUME ["/app/db", "/app/instance"]

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "wsgi:app"]
