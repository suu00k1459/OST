# Dockerfile.xgboost-forecasting
# XGBoost forecasting service for FLEAD

FROM python:3.10-slim

WORKDIR /app

# System dependencies (just in case; wheels should exist for py3.10)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install them + xgboost
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt xgboost>=2.0.0

# Copy forecasting script
COPY scripts/07_xgboost_forecasting.py ./scripts/

# Environment variables for DB (override in docker-compose if needed)
ENV PYTHONUNBUFFERED=1 \
    DB_HOST=timescaledb \
    DB_PORT=5432 \
    DB_NAME=flead \
    DB_USER=flead \
    DB_PASSWORD=password

CMD ["python", "scripts/07_xgboost_forecasting.py"]

