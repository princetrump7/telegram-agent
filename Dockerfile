FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Run in webhook mode (WEBHOOK_URL must be set at runtime)
CMD ["python", "main.py"]
