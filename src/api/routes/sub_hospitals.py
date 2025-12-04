from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from src.core.database import get_db, ClientStatusEnum
from src.core.client_service import ClientService
from src.core.services.db_sub import SubHospitalDBService
from src.models.models import ClientRegistrationRequest, ClientRegistrationResponse
from src.config.settings import settings
import re

router = APIRouter(prefix="/api/hospitals", tags=["Hospitals"])
client_service = ClientService()
db_service = SubHospitalDBService()


@router.post("/{parent_uuid}/sub-hospitals/register", response_model=ClientRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_sub_hospital(parent_uuid: str, request: ClientRegistrationRequest, db: Session = Depends(get_db)):
    parent_hospital = client_service.get_client_by_uuid(db, parent_uuid)
    if not parent_hospital:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Parent hospital not found: {parent_uuid}")
    
    if parent_hospital.status != ClientStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parent hospital deployment not completed. Current status: {parent_hospital.status.value}"
        )
    
    request.parent_uuid = parent_uuid
    
    try:
        client = client_service.create_client(db, request)
        client_service.update_client_status(db, client.uuid, ClientStatusEnum.IN_PROGRESS)
        
        parent_outputs = client_service.parse_terraform_outputs(parent_hospital.terraform_outputs)
        if not parent_outputs or not parent_outputs.private_bucket_name:
            client_service.update_client_status(
                db, client.uuid, ClientStatusEnum.FAILED,
                "Failed to retrieve parent hospital's private bucket name"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent hospital's private bucket name not found in outputs"
            )
        
        region = request.region or settings.gcp_region
        success, result = db_service.create_database(
            parent_uuid, request.client_name, client.uuid,
            parent_outputs.private_bucket_name, region
        )
        
        if success:
            db_name = re.sub(r'[^a-zA-Z0-9_-]', '_', request.client_name.lower())
            db_name = re.sub(r'_+', '_', db_name).strip('_')
            if not db_name:
                db_name = f"sub_{client.uuid[:8]}"
            
            outputs_dict = parent_outputs.dict()
            outputs_dict['database_name'] = db_name
            outputs_dict['connection_uri'] = result
            
            client_service.update_client_outputs(db, client.uuid, outputs_dict)
            client_service.update_client_status(db, client.uuid, ClientStatusEnum.COMPLETED)
            
            try:
                table_success, table_message = db_service.create_tables(
                    client.uuid, parent_uuid, db_name, region, parent_outputs.private_bucket_name
                )
                if not table_success:
                    pass
            except Exception:
                pass
        else:
            client_service.update_client_status(db, client.uuid, ClientStatusEnum.FAILED, result)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result)
        
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to register sub-hospital: {str(e)}")


@router.post("/{hospital_uuid}/sub-hospitals/create-tables")
async def create_sub_tables(hospital_uuid: str, db: Session = Depends(get_db)):
    client = client_service.get_client_by_uuid(db, hospital_uuid)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Hospital not found: {hospital_uuid}")
    
    if client.status != ClientStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Hospital must be in 'completed' status. Current status: {client.status.value}"
        )
    
    if not client.parent_uuid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This endpoint is for sub-hospitals only")
    
    try:
        region = client.region or settings.gcp_region
        parent_hospital = client_service.get_client_by_uuid(db, client.parent_uuid)
        if not parent_hospital:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent hospital not found")
        
        parent_outputs = client_service.parse_terraform_outputs(parent_hospital.terraform_outputs)
        if not parent_outputs or not parent_outputs.private_bucket_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent hospital's private bucket name not found")
        
        terraform_outputs = client_service.parse_terraform_outputs(client.terraform_outputs)
        database_name = terraform_outputs.database_name if terraform_outputs else None
        
        if not database_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Database name not found in outputs")
        
        success, message = db_service.create_tables(
            hospital_uuid, client.parent_uuid, database_name, region, parent_outputs.private_bucket_name
        )
        
        if success:
            return {"message": "Tables created successfully", "hospital_uuid": hospital_uuid, "details": message}
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create tables: {message}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creating tables: {str(e)}")
