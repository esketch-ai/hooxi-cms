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

# Static files middleware - serve React app from /dist
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="/dist"), name="static")

@app.get("/")
async def root():
    """Serve React app for frontend"""
    static_path = "/dist/index.html"
    if os.path.exists(static_path):
        from fastapi.responses import FileResponse
        return FileResponse(static_path)
    
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
