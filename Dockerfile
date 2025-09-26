# Multi-stage build for Python backend and Angular frontend (PRODUCTION)
FROM docker.io/node:20-alpine AS frontend-builder

# Build Angular frontend
WORKDIR /app/frontend
COPY src/ ./src/
COPY package*.json ./
COPY angular.json ./
COPY tsconfig*.json ./

RUN npm ci
RUN npm install -g @angular/cli
RUN npm run build --configuration=production

# Python backend stage
FROM docker.io/python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/
COPY schemas/ ./schemas/

# Copy built frontend from previous stage
COPY --from=frontend-builder /app/frontend/dist/weird-bench-site/browser/ ./static/

# Create data directory
RUN mkdir -p /app/data

# Set environment variables
ENV PYTHONPATH=/app/backend
ENV DATA_DIR=/app/data
ENV HOST=0.0.0.0
ENV PORT=8000

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]