# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

# Copy all source files (node_modules/dist excluded via .dockerignore)
COPY frontend/ ./
# 재무·자산 기능 노출 스위치(기본 on=전체 노출). 운영 빌드만 off로 주입해 은닉.
# Vite는 빌드 시 process.env의 VITE_*가 .env.production보다 우선 → 공유 .env 미변경으로 주입.
ARG FEATURE_FINANCE=on
ENV VITE_FEATURE_FINANCE=$FEATURE_FINANCE
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
