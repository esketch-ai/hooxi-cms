# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

# Copy all source files including index.html (entry point)
COPY frontend/index.html .
COPY frontend/src/. src/
COPY frontend/tsconfig.json .
COPY frontend/vite.config.ts .
COPY frontend/public/. public/
RUN npm run build

# Stage 2: Backend + Static Files
FROM python:3.9-slim

WORKDIR /app

# Copy built frontend files to static directory (preserving folder structure)
COPY --from=frontend-builder /app/frontend/dist ./dist

# Install backend dependencies including uvicorn
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/main.py .

# Expose port 8080 for Cloud Run
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Set PORT environment variable for Cloud Run compatibility
ENV PORT=8080

# Run the application with uvicorn (handles PORT env var automatically on Cloud Run)
CMD ["uvicorn", "main:app:app", "--host", "0.0.0.0", "--port", "80"]
