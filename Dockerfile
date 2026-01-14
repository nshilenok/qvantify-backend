FROM python:3.11-slim

WORKDIR /app

# Install python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Ensure our wrapper scripts take precedence.
ENV PATH="/app/bin:${PATH}"

# Force start.py to run even if Railway has a "Start Command" override configured.
# In Docker, overriding the command replaces CMD but not ENTRYPOINT.
ENTRYPOINT ["python", "start.py"]

