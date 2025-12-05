import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.config.settings import settings
from src.core.database import init_db
from src.api.routes import hospitals, sub_hospitals, common

logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    frontend_path = Path("/app/frontend")
    if frontend_path.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")
        
        @app.get("/", tags=["Frontend"], include_in_schema=False)
        async def serve_frontend():
            return FileResponse(str(frontend_path / "index.html"))
except Exception:
    pass

app.include_router(hospitals.router)
app.include_router(sub_hospitals.router)
app.include_router(common.router)


@app.get("/api", tags=["Root"])
async def api_info():
    return {
        "message": "Multi-Client Terraform Provisioning API",
        "version": settings.api_version,
        "endpoints": {
            "register": "POST /api/hospitals/register",
            "status": "GET /api/hospitals/{uuid}/status",
            "outputs": "GET /api/clients/{uuid}/outputs",
            "list": "GET /api/hospitals"
        }
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
