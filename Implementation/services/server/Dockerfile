FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/common/ ./common/
COPY services/server/server.py ./
ENV PYTHONUNBUFFERED=1
CMD ["python", "server.py"]