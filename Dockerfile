# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

# Copy all source files (node_modules/dist excluded via .dockerignore)
COPY frontend/ ./
RUN npm run build

# Stage 2: Backend + Static Files
FROM python:3.9-slim

WORKDIR /app

# Copy built frontend files to static directory (preserving folder structure)
COPY --from=frontend-builder /app/frontend/dist ./dist

# Install backend dependencies including uvicorn
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code (routers/, services/, scripts/ 포함 — .dockerignore가 .venv·tests 제외)
COPY backend/ ./

# Expose port 8080 for Cloud Run
EXPOSE 8080

# Set PORT environment variable for Cloud Run compatibility
ENV PORT=8080

# Run the application with uvicorn (manually bind to the PORT environment variable)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
