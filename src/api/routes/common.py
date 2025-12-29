from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from src.core.database import get_db, ClientStatusEnum
from src.core.client_service import ClientService
from src.core.terraform_service import TerraformService
from src.models.models import ClientListResponse, ClientStatusResponse
from src.api.middleware.auth import verify_api_key
from src.config.settings import settings

router = APIRouter(tags=["Common"], dependencies=[Depends(verify_api_key)])
client_service = ClientService()
terraform_service = TerraformService()


@router.get("/api/hospitals", response_model=ClientListResponse)
async def list_hospitals(db: Session = Depends(get_db)):
    clients = client_service.get_all_clients(db)
    from src.models.models import ClientListItem
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
    return ClientListResponse(clients=client_items, total=len(client_items))


@router.get("/api/clients/{client_uuid}/status", response_model=ClientStatusResponse)
async def get_client_status(client_uuid: str, db: Session = Depends(get_db)):
    client = client_service.get_client_by_uuid(db, client_uuid)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Client not found: {client_uuid}")
    
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


@router.get("/api/clients/{client_uuid}/outputs")
async def get_client_outputs(client_uuid: str, db: Session = Depends(get_db)):
    client = client_service.get_client_by_uuid(db, client_uuid)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Client not found: {client_uuid}")
    
    if client.status != ClientStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Deployment not completed. Current status: {client.status.value}"
        )
    
    terraform_outputs = client_service.parse_terraform_outputs(client.terraform_outputs)
    if not terraform_outputs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No outputs available for this client")
    
    return terraform_outputs


@router.delete("/api/clients/{client_uuid}")
async def delete_client(client_uuid: str, skip_infrastructure: bool = False, db: Session = Depends(get_db)):
    client = client_service.get_client_by_uuid(db, client_uuid)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Client not found: {client_uuid}")
    
    if not client.parent_uuid:
        sub_hospitals = client_service.get_sub_hospitals(db, client_uuid)
        for sub_hospital in sub_hospitals:
            if not skip_infrastructure:
                client_service.update_client_status(db, sub_hospital.uuid, ClientStatusEnum.IN_PROGRESS)
                sub_success, sub_error = terraform_service.destroy_client_infrastructure(sub_hospital.uuid)
                if not sub_success:
                    print(f"Warning: Failed to destroy sub-hospital {sub_hospital.uuid} infrastructure: {sub_error}")
            
            db.delete(sub_hospital)
            db.commit()
    
    if not skip_infrastructure:
        client_service.update_client_status(db, client_uuid, ClientStatusEnum.IN_PROGRESS)
        success, error_message = terraform_service.destroy_client_infrastructure(client_uuid)
        
        if not success:
            if client.status == ClientStatusEnum.FAILED:
                skip_infrastructure = True
            else:
                client_service.update_client_status(db, client_uuid, ClientStatusEnum.FAILED, f"Infrastructure destruction failed: {error_message}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to destroy infrastructure: {error_message}")
    
    db.delete(client)
    db.commit()
    
    return {
        "message": f"Client {client_uuid} deleted successfully",
        "client_uuid": client_uuid,
        "infrastructure_destroyed": not skip_infrastructure
    }


@router.post("/api/clients/{client_uuid}/destroy-infrastructure")
async def destroy_infrastructure_only(client_uuid: str, db: Session = Depends(get_db)):
    success, error_message = terraform_service.destroy_client_infrastructure(client_uuid)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to destroy infrastructure: {error_message or 'Unknown error'}"
        )
    
    return {
        "message": f"Infrastructure destroyed successfully for {client_uuid}",
        "client_uuid": client_uuid
    }

