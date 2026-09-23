FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim AS runner

WORKDIR /workspace

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY ./app /workspace/app
COPY .env .env

EXPOSE 8000

CMD ["fastapi", "run", "app/main.py", "--port", "8000"]