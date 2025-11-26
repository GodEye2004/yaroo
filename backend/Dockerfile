# Use Python 3.11 slim
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for PDF, OCR, OpenCV, etc.
RUN apt-get update && apt-get install -y \
    build-essential \
    tesseract-ocr \
    tesseract-ocr-fas \
    poppler-utils \
    libglib2.0-0 \
    libgl1 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Install additional packages (if needed)
RUN pip install --no-cache-dir \
    unstructured \
    unstructured-inference \
    langchain \
    langchain-community \
    pillow \
    opencv-python-headless \
    easyocr \
    matplotlib \
    beautifulsoup4 \
    chardet \
    python-docx \
    httpx \
    hazm \
    python-dotenv \
    asyncpg \
    "sqlalchemy[asyncio]"

# Download NLTK data
RUN python3 -c "import nltk; \
    nltk.download('punkt'); \
    nltk.download('punkt_tab'); \
    nltk.download('averaged_perceptron_tagger'); \
    nltk.download('averaged_perceptron_tagger_eng')"

# Copy backend code
COPY . .

# Expose port
EXPOSE 8000

# Run app with uvicorn
CMD ["uvicorn", "test:app", "--host", "0.0.0.0", "--port", "8000"]
