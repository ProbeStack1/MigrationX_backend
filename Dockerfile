FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run will pass the PORT
ENV PORT=8080

# Start FastAPI via uvicorn
CMD ["python", "server.py"]