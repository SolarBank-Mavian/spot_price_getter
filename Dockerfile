FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY fetch_15min_data.py .

# Run the script
CMD ["python", "fetch_15min_data.py"]

