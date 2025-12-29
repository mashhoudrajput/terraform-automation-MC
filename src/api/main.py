import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config.settings import settings
from src.core.database import init_db
from src.core.db_backup import download_db_snapshot, start_periodic_backup, stop_periodic_backup
from src.api.routes import hospitals, sub_hospitals, common

logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import threading
    download_complete = threading.Event()
    
    def download_with_timeout():
        try:
            download_db_snapshot()
        except Exception as e:
            logger.warning(f"Database download failed: {e}. Starting with empty database.")
        finally:
            download_complete.set()
    
    download_thread = threading.Thread(target=download_with_timeout, daemon=True)
    download_thread.start()
    download_complete.wait(timeout=10)
    
    init_db()
    start_periodic_backup()
    try:
        yield
    finally:
        stop_periodic_backup(run_final_upload=True)


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

@app.get("/", tags=["Root"], include_in_schema=False)
async def root():
    return {"message": "Backend service running"}

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
