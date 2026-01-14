FROM python:3.11-slim

WORKDIR /app

# Install python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Railway provides PORT; default is handled in start.py for local runs.
CMD ["python", "start.py"]

