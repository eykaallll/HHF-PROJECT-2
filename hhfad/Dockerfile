FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SSH_PASSWORD=helperpass123

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-server nano gosu \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/run/sshd

RUN mkdir -p /etc/ssh/sshd_config.d \
    && printf "PasswordAuthentication yes\nChallengeResponseAuthentication no\nUsePAM yes\nPubkeyAuthentication yes\n" \
        > /etc/ssh/sshd_config.d/90-password.conf

RUN adduser --disabled-password --gecos "" appuser \
    && adduser --disabled-password --gecos ""  ctf

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chown -R appuser:appuser /app

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV FLASK_APP=app.py \
    PORT=8001 \
    SSH_PORT=2222

EXPOSE 8001 2222

ENTRYPOINT ["/entrypoint.sh"]
