# Use a lightweight Python image
FROM python:3.11-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

# Copy all your local files (your "many files") into the container
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install any dependencies (ensure you have a requirements.txt)
# If you don't have one, run: pip freeze > requirements.txt locally first
RUN pip install --no-cache-dir -r requirements.txt

# Cloud Run will set an environment variable "PORT" (usually 8080).
# Your server.py MUST listen on this port.
CMD ["python", "server.py"]