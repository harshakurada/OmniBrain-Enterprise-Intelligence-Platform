# ==============================================================================
# OmniBrain - Central Dockerfile
# ==============================================================================

# Use official lightweight Python 3.12 image
FROM python:3.12-slim

# Prevent Python from writing pyc files to disc
ENV PYTHONDONTWRITEBYTECODE=1

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1

# Set the working directory in container
WORKDIR /workspace

# Install system dependencies (e.g. compile-time dependencies, curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt to install dependencies
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the entire project repository
COPY . .

# Ensure the log folder directory exists
RUN mkdir -p logs

# Expose FastAPI backend and Streamlit frontend ports
EXPOSE 8000
EXPOSE 8501

# Default command (intended to be overridden in docker-compose.yml)
CMD ["python"]
