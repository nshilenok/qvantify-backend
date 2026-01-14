FROM python:3.11-slim

WORKDIR /app

# Install python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Railway provides PORT; default for local Docker runs
ENV PORT=5000

CMD ["sh", "-c", "python -m gunicorn server:app --bind 0.0.0.0:$PORT"]

