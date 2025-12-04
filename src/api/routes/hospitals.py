from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from src.core.database import get_db, ClientStatusEnum
from src.core.client_service import ClientService
from src.core.terraform_service import TerraformService
from src.core.services.db_main import MainHospitalDBService
from src.models.models import ClientRegistrationRequest, ClientRegistrationResponse, ClientStatusResponse
from src.api.error_handler import enhance_terraform_error
from src.config.settings import settings

router = APIRouter(prefix="/api/hospitals", tags=["Hospitals"])
client_service = ClientService()
terraform_service = TerraformService()
db_service = MainHospitalDBService()


@router.post("/register", response_model=ClientRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_hospital(request: ClientRegistrationRequest, db: Session = Depends(get_db)):
    try:
        client = client_service.create_client(db, request)
        client_service.update_client_status(db, client.uuid, ClientStatusEnum.IN_PROGRESS)
        
        client_info = {
            "client_name": request.client_name,
            "environment": request.environment,
            "region": request.region,
            "parent_uuid": request.parent_uuid
        }
        
        success, outputs, error_message = terraform_service.run_full_deployment(client.uuid, client_info)
        
        if success:
            client_service.update_client_outputs(db, client.uuid, outputs)
            client_service.update_client_status(db, client.uuid, ClientStatusEnum.COMPLETED)
            
            try:
                region = request.region or settings.gcp_region
                terraform_outputs = client_service.parse_terraform_outputs(
                    client_service.get_client_by_uuid(db, client.uuid).terraform_outputs
                )
                private_bucket_name = terraform_outputs.private_bucket_name if terraform_outputs else None
                
                if private_bucket_name:
                    table_success, table_message = db_service.create_tables(
                        client.uuid, region, private_bucket_name
                    )
                    if not table_success:
                        pass
            except Exception:
                pass
        else:
            enhanced_error = enhance_terraform_error(error_message)
            client_service.update_client_status(db, client.uuid, ClientStatusEnum.FAILED, enhanced_error)
        
        client = client_service.get_client_by_uuid(db, client.uuid)
        return ClientRegistrationResponse(
            client_uuid=client.uuid,
            job_id=client.job_id,
            status=client_service.map_db_status_to_api_status(client.status),
            status_url=f"/api/clients/{client.uuid}/status",
            created_at=client.created_at
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to register hospital: {str(e)}")


@router.get("/{hospital_uuid}/status", response_model=ClientStatusResponse)
async def get_hospital_status(hospital_uuid: str, db: Session = Depends(get_db)):
    client = client_service.get_client_by_uuid(db, hospital_uuid)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Hospital not found: {hospital_uuid}")
    
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


@router.post("/{hospital_uuid}/create-tables")
async def create_tables(hospital_uuid: str, db: Session = Depends(get_db)):
    client = client_service.get_client_by_uuid(db, hospital_uuid)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Hospital not found: {hospital_uuid}")
    
    if client.status != ClientStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Hospital must be in 'completed' status. Current status: {client.status.value}"
        )
    
    try:
        region = client.region or settings.gcp_region
        terraform_outputs = client_service.parse_terraform_outputs(client.terraform_outputs)
        private_bucket_name = terraform_outputs.private_bucket_name if terraform_outputs else None
        
        if not private_bucket_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Private bucket name not found in outputs"
            )
        
        success, message = db_service.create_tables(hospital_uuid, region, private_bucket_name)
        
        if success:
            return {"message": "Tables created successfully", "hospital_uuid": hospital_uuid, "details": message}
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create tables: {message}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creating tables: {str(e)}")

