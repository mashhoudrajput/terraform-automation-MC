FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG TERRAFORM_VERSION=1.6.6
RUN wget -q https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip \
    && unzip -q terraform_${TERRAFORM_VERSION}_linux_amd64.zip \
    && mv terraform /usr/local/bin/terraform \
    && rm terraform_${TERRAFORM_VERSION}_linux_amd64.zip \
    && chmod +x /usr/local/bin/terraform

WORKDIR /app
COPY src/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && find /usr/local/lib/python3.11/site-packages -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true \
    && find /usr/local/lib/python3.11/site-packages -name "*.pyc" -delete

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    openssh-client \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update && apt-get install -y --no-install-recommends google-cloud-sdk \
    && apt-get purge -y gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /root/.cache \
    && rm -rf /tmp/* \
    && rm -rf /var/tmp/*

COPY --from=builder /usr/local/bin/terraform /usr/local/bin/terraform
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app
COPY src/ ./src/
COPY infrastructure/ ./infrastructure/
COPY .env /app/.env
COPY deploy/docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh && mkdir -p /data

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
