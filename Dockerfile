FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git libxml2-dev libxslt-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir poetry && poetry install --no-root --only main
COPY sentiment_cli_bot ./sentiment_cli_bot
ENTRYPOINT ["poetry", "run", "bot", "live"]
