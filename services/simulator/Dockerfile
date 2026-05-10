FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source (overridden by volume mount in development)
COPY . .

CMD ["python", "simulator.py"]
