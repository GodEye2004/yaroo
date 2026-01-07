# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Set work directory
WORKDIR /app

# Install system dependencies
# libgl1 and libglib2.0-0 are required for opencv/rapidocr
RUN apt-get update && apt-get install -y     gcc     g++     libpq-dev     poppler-utils     libgl1     libglib2.0-0     && apt-get clean     && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install python dependencies
RUN pip install --upgrade pip &&     pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create directories for uploads/temp if they don't exist
RUN mkdir -p /app/uploads /app/temp

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
