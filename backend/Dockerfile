FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for OpenCV, Tesseract, and PDF processing
RUN apt-get update && apt-get install -y \
    build-essential \
    tesseract-ocr \
    tesseract-ocr-fas \
    poppler-utils \
    libglib2.0-0 \
    libgl1 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY ../requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install NLTK data - ADD THE MISSING PACKAGES HERE
RUN python3 -c "import nltk; \
    nltk.download('punkt'); \
    nltk.download('punkt_tab'); \
    nltk.download('averaged_perceptron_tagger'); \
    nltk.download('averaged_perceptron_tagger_eng')"

# Install additional packages for OCR and unstructured PDFs
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
    sqlalchemy[asyncio]

# Copy backend code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "test:app", "--host", "0.0.0.0", "--port", "8000"]