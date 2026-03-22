FROM python:3.11-slim-bookworm

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy all source first (needed for pip install)
COPY pyproject.toml .
COPY app/ app/

# Install Python dependencies (non-editable)
RUN pip install --no-cache-dir .

# Copy remaining files (alembic, tests, etc.)
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
