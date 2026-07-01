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

# Install backend dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/main.py .

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Run the application with static files enabled
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
