# Use Python 3.12 slim image as base
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./

# Install pip and setuptools
RUN pip install --no-cache-dir --upgrade pip setuptools

# Install project dependencies directly from pyproject.toml
RUN pip install --no-cache-dir \
    "fastapi>=0.121.3,<0.122.0" \
    "uvicorn>=0.38.0,<0.39.0" \
    "python-dotenv==1.0.0" \
    "pydantic>=2.12.4,<3.0.0" \
    "pydantic-settings>=2.0.0,<3.0.0" \
    "yt-dlp==2025.10.14" \
    "openai>=1.0.0,<2.0.0" \
    "tavily-python>=0.5.0,<1.0.0" \
    "httpx>=0.28.0,<1.0.0"

# Copy application code
COPY . .

# Expose port (Fly.io will handle the actual port binding)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application with uvicorn
# Fly.io sets PORT environment variable, default to 8080
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}

