FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source (overridden by volume mount in development)
COPY . .

EXPOSE 8000

# --reload enables hot-reload when source is volume-mounted
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
