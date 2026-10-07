FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as an unprivileged user
RUN useradd --system --uid 10001 --no-create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
# Apply migrations, then serve. --proxy-headers is left off: the app decides which
# proxies to trust itself (TRUSTED_PROXIES).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
