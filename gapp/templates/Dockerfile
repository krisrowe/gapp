FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

COPY . /app

RUN uv pip install --system "mcp[cli]" uvicorn \
    && uv pip install --system -e .

ARG ENTRYPOINT
ENV ENTRYPOINT=${ENTRYPOINT}

EXPOSE 8080

CMD ["sh", "-c", "uvicorn ${ENTRYPOINT} --host 0.0.0.0 --port 8080"]
