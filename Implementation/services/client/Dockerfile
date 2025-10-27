FROM tensorflow/tensorflow:2.16.1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/common/ ./common/
COPY services/client/client.py ./
ENV PYTHONUNBUFFERED=1
CMD ["python", "client.py"]