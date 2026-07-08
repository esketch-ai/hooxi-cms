from fastapi import FastAPI, Request
import os

# Initialize FastAPI app
app = FastAPI(
    title="Hooxi CMS API",
    description="Carbon Fleet Management System API",
    version="1.0.0"
)

# CORS middleware for frontend connection
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Resolve the path to the frontend build output (dist)
# Supports both Docker environment (/app/dist) and local development
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
dist_path = "/app/dist"
if not os.path.exists(dist_path):
    dist_path = os.path.join(os.path.dirname(BASE_DIR), "frontend", "dist")
if not os.path.exists(dist_path):
    dist_path = os.path.join(BASE_DIR, "dist")

# Static files middleware - serve React app if dist directory exists
from fastapi.staticfiles import StaticFiles
if os.path.exists(dist_path):
    app.mount("/static", StaticFiles(directory=dist_path), name="static")
else:
    print(f"Warning: static dist folder not found at {dist_path}")

@app.get("/")
async def root():
    """Serve React app for frontend"""
    index_path = os.path.join(dist_path, "index.html")
    if os.path.exists(index_path):
        from fastapi.responses import FileResponse
        return FileResponse(index_path)
    
    # Fallback to API response if no static files found
    return {"Hello": "World", "API": "Hooxi CMS v1.0"}

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": __import__('datetime').now().isoformat(),
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
