"""
Multi-Client Terraform Provisioning API
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.core.database import init_db, get_db, Client, ClientStatusEnum
from src.models.models import (
    ClientRegistrationRequest,
    ClientRegistrationResponse,
    ClientStatusResponse,
    ClientListResponse,
    ClientListItem,
    ErrorResponse,
)
from src.core.client_service import ClientService
from src.core.terraform_service import TerraformService
from src.core.database_service import DatabaseService
from src.api.error_handler import enhance_terraform_error

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
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
            """Serve the frontend HTML page."""
            return FileResponse(str(frontend_path / "index.html"))
except Exception as e:
    logger.warning(f"Frontend not available: {e}")

terraform_service = TerraformService()
client_service = ClientService()
database_service = DatabaseService()


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
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
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": "2025-11-25T10:00:00Z"}


@app.post(
    "/api/hospitals/register",
    response_model=ClientRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Hospitals"]
)
async def register_hospital(
    request: ClientRegistrationRequest,
    db: Session = Depends(get_db)
):
    """
    Register a new hospital and provision isolated GCP infrastructure.
    
    This endpoint:
    1. Creates a unique UUID for the hospital
    2. Creates Cloud SQL database
    3. Initializes database tables automatically
    4. Saves connection string in Secret Manager
    5. Returns hospital UUID and job ID for status tracking
    
    The deployment runs synchronously and may take 5-10 minutes.
    Database tables are automatically created after database provisioning.
    """
    return await register_client(request, db)


@app.post(
    "/api/clients/register",
    response_model=ClientRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Clients"]
)
async def register_client(
    request: ClientRegistrationRequest,
    db: Session = Depends(get_db)
):
    """
    Register a new client and provision isolated GCP infrastructure.
    
    This endpoint:
    1. Creates a unique UUID for the client
    2. Initializes isolated Terraform workspace
    3. Executes Terraform apply synchronously
    4. Returns client UUID and job ID for status tracking
    
    The deployment runs synchronously and may take 5-10 minutes.
    """
    try:
        client = client_service.create_client(db, request)
        logger.info(f"Registered client: {client.uuid} - {request.client_name}")
        client_service.update_client_status(db, client.uuid, ClientStatusEnum.IN_PROGRESS)
        client_info = {
            "client_name": request.client_name,
            "environment": request.environment,
            "region": request.region,
            "parent_uuid": request.parent_uuid
        }
        
        logger.info(f"Starting Terraform deployment for client {client.uuid}")
        success, outputs, error_message = terraform_service.run_full_deployment(
            client.uuid,
            client_info
        )
        
        if success:
            client_service.update_client_outputs(db, client.uuid, outputs)
            client_service.update_client_status(db, client.uuid, ClientStatusEnum.COMPLETED)
            logger.info(f"Deployment completed successfully for client {client.uuid}")
            
            # Automatically create tables after successful deployment
            try:
                logger.info(f"Automatically creating tables for client {client.uuid}...")
                is_sub_hospital = request.parent_uuid is not None
                region = request.region or settings.gcp_region
                
                # Get private bucket name from outputs
                terraform_outputs = client_service.parse_terraform_outputs(
                    client_service.get_client_by_uuid(db, client.uuid).terraform_outputs
                )
                private_bucket_name = terraform_outputs.private_bucket_name if terraform_outputs else None
                
                if private_bucket_name:
                    db_name = terraform_outputs.database_name if terraform_outputs else None
                    parent_uuid = client.parent_uuid if is_sub_hospital else None
                    
                    table_success, table_message = database_service.create_tables(
                        client.uuid, 
                        is_sub_hospital, 
                        region, 
                        private_bucket_name,
                        parent_uuid=parent_uuid,
                        database_name=db_name
                    )
                    if table_success:
                        logger.info(f"Tables created successfully for client {client.uuid}")
                    else:
                        logger.warning(f"Automatic table creation failed for client {client.uuid}: {table_message}")
                        # Don't fail the registration, just log the warning
                else:
                    logger.warning(f"Could not create tables automatically: private_bucket_name not found in outputs")
            except Exception as e:
                logger.error(f"Error during automatic table creation: {str(e)}", exc_info=True)
                # Don't fail the registration if table creation fails
        else:
            enhanced_error = enhance_terraform_error(error_message)
            client_service.update_client_status(
                db, 
                client.uuid, 
                ClientStatusEnum.FAILED,
                enhanced_error
            )
            logger.error(f"Deployment failed for client {client.uuid}: {error_message}")
        
        client = client_service.get_client_by_uuid(db, client.uuid)
        
        return ClientRegistrationResponse(
            client_uuid=client.uuid,
            job_id=client.job_id,
            status=client_service.map_db_status_to_api_status(client.status),
            status_url=f"/api/clients/{client.uuid}/status",
            created_at=client.created_at
        )
        
    except Exception as e:
        logger.error(f"Error registering client: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register client: {str(e)}"
        )


@app.get(
    "/api/hospitals/{hospital_uuid}/status",
    response_model=ClientStatusResponse,
    tags=["Hospitals"]
)
async def get_hospital_status(
    hospital_uuid: str,
    db: Session = Depends(get_db)
):
    """
    Get the deployment status for a hospital.
    
    Returns:
    - Hospital information
    - Database creation status (in_progress, completed, failed)
    - Connection string location in Secret Manager
    """
    return await get_client_status(hospital_uuid, db)


@app.get(
    "/api/clients/{client_uuid}/status",
    response_model=ClientStatusResponse,
    tags=["Clients"]
)
async def get_client_status(
    client_uuid: str,
    db: Session = Depends(get_db)
):
    """
    Get the deployment status and details for a specific client.
    
    Returns:
    - Client information
    - Deployment status (pending, in_progress, completed, failed)
    - Terraform outputs (if deployment completed)
    - Error message (if deployment failed)
    """
    client = client_service.get_client_by_uuid(db, client_uuid)
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client not found: {client_uuid}"
        )
    
    terraform_outputs = client_service.parse_terraform_outputs(client.terraform_outputs)
    
    return ClientStatusResponse(
        client_uuid=client.uuid,
        client_name=client.client_name,
        job_id=client.job_id,
        status=client_service.map_db_status_to_api_status(client.status),
        environment=client.environment,
        region=client.region,
        created_at=client.created_at,
        updated_at=client.updated_at,
        error_message=client.error_message,
        terraform_outputs=terraform_outputs
    )


@app.get(
    "/api/clients/{client_uuid}/outputs",
    tags=["Clients"]
)
async def get_client_outputs(
    client_uuid: str,
    db: Session = Depends(get_db)
):
    """
    Get Terraform outputs for a specific client.
    
    This endpoint returns the infrastructure details created for the client,
    including database connection information, storage buckets, etc.
    
    Only available after deployment is completed.
    """
    client = client_service.get_client_by_uuid(db, client_uuid)
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client not found: {client_uuid}"
        )
    
    if client.status != ClientStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Deployment not completed. Current status: {client.status.value}"
        )
    
    terraform_outputs = client_service.parse_terraform_outputs(client.terraform_outputs)
    
    if not terraform_outputs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No outputs available for this client"
        )
    
    return terraform_outputs


@app.get(
    "/api/hospitals",
    response_model=ClientListResponse,
    tags=["Hospitals"]
)
async def list_hospitals(db: Session = Depends(get_db)):
    """
    List all registered hospitals with their current status.
    
    Returns a list of all hospitals ordered by creation date (most recent first).
    """
    return await list_clients(db)


@app.get(
    "/api/clients",
    response_model=ClientListResponse,
    tags=["Clients"]
)
async def list_clients(db: Session = Depends(get_db)):
    """
    List all registered clients with their current status.
    
    Returns a list of all clients ordered by creation date (most recent first).
    """
    clients = client_service.get_all_clients(db)
    
    client_items = [
        ClientListItem(
            client_uuid=client.uuid,
            client_name=client.client_name,
            status=client_service.map_db_status_to_api_status(client.status),
            environment=client.environment,
            region=client.region,
            parent_uuid=client.parent_uuid,
            created_at=client.created_at
        )
        for client in clients
    ]
    
    return ClientListResponse(
        clients=client_items,
        total=len(client_items)
    )


@app.post(
    "/api/hospitals/{parent_uuid}/sub-hospitals/register",
    response_model=ClientRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Hospitals"]
)
async def register_sub_hospital(
    parent_uuid: str,
    request: ClientRegistrationRequest,
    db: Session = Depends(get_db)
):
    """
    Register a new sub-hospital under a parent hospital.
    
    This endpoint:
    1. Validates the parent hospital exists and is completed
    2. Creates a new database in the parent's Cloud SQL instance
    3. Uses parent's infrastructure (buckets, secrets)
    
    The deployment runs synchronously and may take 3-5 minutes.
    """
    parent_hospital = client_service.get_client_by_uuid(db, parent_uuid)
    if not parent_hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parent hospital not found: {parent_uuid}"
        )
    
    if parent_hospital.status != ClientStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parent hospital deployment not completed. Current status: {parent_hospital.status.value}"
        )
    
    request.parent_uuid = parent_uuid
    
    try:
        client = client_service.create_client(db, request)
        logger.info(f"Registered sub-hospital: {client.uuid} - {request.client_name} under parent {parent_uuid}")
        client_service.update_client_status(db, client.uuid, ClientStatusEnum.IN_PROGRESS)
        
        logger.info(f"Creating database for sub-hospital {client.uuid} in parent {parent_uuid}'s MySQL instance")
        
        # Get parent's private bucket name from outputs
        parent_outputs = client_service.parse_terraform_outputs(parent_hospital.terraform_outputs)
        if not parent_outputs or not parent_outputs.private_bucket_name:
            client_service.update_client_status(
                db, 
                client.uuid, 
                ClientStatusEnum.FAILED,
                "Failed to retrieve parent hospital's private bucket name"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent hospital's private bucket name not found in outputs"
            )
        
        region = request.region or settings.gcp_region
        success, result = database_service.create_sub_hospital_database(
            parent_uuid,
            request.client_name,
            client.uuid,
            private_bucket_name=parent_outputs.private_bucket_name,
            region=region
        )
        
        if success:
            parent_outputs = client_service.parse_terraform_outputs(parent_hospital.terraform_outputs)
            if parent_outputs:
                import re
                db_name = re.sub(r'[^a-zA-Z0-9_-]', '_', request.client_name.lower())
                db_name = re.sub(r'_+', '_', db_name).strip('_')
                if not db_name:
                    db_name = f"sub_{client.uuid[:8]}"
                
                outputs_dict = parent_outputs.dict()
                outputs_dict['database_name'] = db_name
                outputs_dict['connection_uri'] = result
                
                client_service.update_client_outputs(db, client.uuid, outputs_dict)
                client_service.update_client_status(db, client.uuid, ClientStatusEnum.COMPLETED)
                logger.info(f"Sub-hospital database created successfully for client {client.uuid}")
            else:
                client_service.update_client_status(
                    db, 
                    client.uuid, 
                    ClientStatusEnum.FAILED,
                    "Failed to retrieve parent hospital outputs"
                )
        else:
            client_service.update_client_status(
                db, 
                client.uuid, 
                ClientStatusEnum.FAILED,
                result
            )
            logger.error(f"Sub-hospital database creation failed for client {client.uuid}: {result}")
        
        client = client_service.get_client_by_uuid(db, client.uuid)
        
        return ClientRegistrationResponse(
            client_uuid=client.uuid,
            job_id=client.job_id,
            status=client_service.map_db_status_to_api_status(client.status),
            status_url=f"/api/clients/{client.uuid}/status",
            created_at=client.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering sub-hospital: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register sub-hospital: {str(e)}"
    )


@app.delete(
    "/api/clients/{client_uuid}",
    tags=["Clients"]
)
async def delete_client(
    client_uuid: str,
    skip_infrastructure: bool = False,
    db: Session = Depends(get_db)
):
    """
    Delete a client and destroy all associated infrastructure.
    
    This endpoint:
    1. Destroys all Terraform-managed infrastructure (Cloud SQL, GCS, etc.) - unless skip_infrastructure=True
    2. Removes the client record from the database
    
    The destruction process may take 5-10 minutes.
    
    Parameters:
    - skip_infrastructure: If True, skip infrastructure destruction and only delete database record
    """
    client = client_service.get_client_by_uuid(db, client_uuid)
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client not found: {client_uuid}"
        )
    
    if not skip_infrastructure:
        client_service.update_client_status(db, client_uuid, ClientStatusEnum.IN_PROGRESS)
        logger.info(f"Starting infrastructure destruction for client {client_uuid}")
        success, error_message = terraform_service.destroy_client_infrastructure(client_uuid)
        
        if not success:
            if client.status == ClientStatusEnum.FAILED:
                logger.warning(f"Infrastructure destroy failed for failed client {client_uuid}, deleting record anyway")
                skip_infrastructure = True
            else:
                client_service.update_client_status(
                    db,
                    client_uuid,
                    ClientStatusEnum.FAILED,
                    f"Infrastructure destruction failed: {error_message}"
                )
                
                logger.error(f"Infrastructure destruction failed for client {client_uuid}: {error_message}")
                
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to destroy infrastructure: {error_message}"
        )
    
    db.delete(client)
    db.commit()
    logger.info(f"Client {client_uuid} deleted successfully")
    
    return {
        "message": f"Client {client_uuid} deleted successfully",
        "client_uuid": client_uuid,
        "infrastructure_destroyed": not skip_infrastructure
    }


@app.post(
    "/api/hospitals/{hospital_uuid}/create-tables",
    tags=["Hospitals"]
)
async def create_tables(
    hospital_uuid: str,
    db: Session = Depends(get_db)
):
    """
    Create database tables for a hospital using ClusterDB.sql.
    
    This endpoint:
    1. Retrieves the database connection URI from Secret Manager
    2. Executes ClusterDB.sql to create all tables
    3. Returns success or error message
    
    The hospital must be in 'completed' status.
    """
    client = client_service.get_client_by_uuid(db, hospital_uuid)
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital not found: {hospital_uuid}"
        )
    
    if client.status != ClientStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Hospital must be in 'completed' status. Current status: {client.status.value}"
        )
    
    logger.info(f"Creating tables for hospital {hospital_uuid}")
    
    try:
        is_sub_hospital = client.parent_uuid is not None
        region = client.region or settings.gcp_region
        
        terraform_outputs = client_service.parse_terraform_outputs(client.terraform_outputs)
        private_bucket_name = None
        database_name = None
        parent_uuid = None
        
        if is_sub_hospital and client.parent_uuid:
            parent_uuid = client.parent_uuid
            parent_hospital = client_service.get_client_by_uuid(db, client.parent_uuid)
            if parent_hospital and parent_hospital.terraform_outputs:
                parent_outputs = client_service.parse_terraform_outputs(parent_hospital.terraform_outputs)
                if parent_outputs:
                    private_bucket_name = parent_outputs.private_bucket_name
            if terraform_outputs:
                database_name = terraform_outputs.database_name
        elif terraform_outputs:
            private_bucket_name = terraform_outputs.private_bucket_name
            database_name = terraform_outputs.database_name
        
        if not private_bucket_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Private bucket name not found. Available outputs: {list(terraform_outputs.dict().keys()) if terraform_outputs else 'None'}"
            )
        
        success, message = database_service.create_tables(
            hospital_uuid, 
            is_sub_hospital, 
            region, 
            private_bucket_name,
            parent_uuid=parent_uuid,
            database_name=database_name
        )
        
        if success:
            logger.info(f"Tables created successfully for hospital {hospital_uuid}")
            return {
                "message": "Tables created successfully",
                "hospital_uuid": hospital_uuid,
                "details": message
            }
        else:
            logger.error(f"Failed to create tables for hospital {hospital_uuid}: {message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create tables: {message}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error creating tables: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

