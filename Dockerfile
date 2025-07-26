FROM python:3.11-slim

# GitHub Container Registry annotations  
LABEL org.opencontainers.image.source=https://github.com/petrouv/teleflux
LABEL org.opencontainers.image.description="Synchronize Telegram channels with Miniflux categories via RssHub"
LABEL org.opencontainers.image.licenses=MIT

ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY teleflux/ teleflux/

RUN pip install --no-cache-dir .
RUN apt-get purge -y --auto-remove build-essential gcc && rm -rf /var/lib/apt/lists/*

RUN useradd --uid 1000 --create-home --shell /bin/bash teleflux \
    && chown -R 1000:1000 /app
USER 1000:1000

CMD ["python", "-m", "teleflux", "--config", "/app/config/config.yml"]