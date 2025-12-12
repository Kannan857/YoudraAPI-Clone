FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/nonroot/.local/bin:${PATH}"

WORKDIR /app

# System deps for common Python packages (psycopg2, etc.)
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Use a non-root user for safety
RUN useradd -m nonroot && chown -R nonroot:nonroot /app
USER nonroot

# Fly will set PORT; default to 8080 locally
ENV PORT=8080 \
    WEB_CONCURRENCY=4

EXPOSE 8080

CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY:-4} -b 0.0.0.0:${PORT:-8080} main:app"]
