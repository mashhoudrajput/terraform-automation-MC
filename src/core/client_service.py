import json
import logging
from typing import Optional, List
from sqlalchemy.orm import Session
from src.core.database import Client, ClientStatusEnum
from src.models.models import ClientRegistrationRequest, ClientStatus, TerraformOutputs

logger = logging.getLogger(__name__)


class ClientService:
    @staticmethod
    def create_client(db: Session, request: ClientRegistrationRequest) -> Client:
        if ClientService.get_client_by_uuid(db, request.client_uuid):
            raise ValueError(f"Client with UUID {request.client_uuid} already exists")
        
        job_id = f"job-{request.client_uuid}"
        client = Client(
            uuid=request.client_uuid,
            client_name=request.client_name,
            job_id=job_id,
            status=ClientStatusEnum.PENDING,
            environment=request.environment,
            region=request.region,
            parent_uuid=request.parent_uuid,
            terraform_outputs=None,
            error_message=None
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        logger.info(f"Created client: {client.uuid} ({client.client_name})")
        return client
    
    @staticmethod
    def get_sub_hospitals(db: Session, parent_uuid: str) -> List[Client]:
        return db.query(Client).filter(Client.parent_uuid == parent_uuid).order_by(Client.created_at.desc()).all()
    
    @staticmethod
    def get_client_by_uuid(db: Session, client_uuid: str) -> Optional[Client]:
        return db.query(Client).filter(Client.uuid == client_uuid).first()
    
    @staticmethod
    def get_client_by_job_id(db: Session, job_id: str) -> Optional[Client]:
        return db.query(Client).filter(Client.job_id == job_id).first()
    
    @staticmethod
    def get_all_clients(db: Session) -> List[Client]:
        return db.query(Client).order_by(Client.created_at.desc()).all()
    
    @staticmethod
    def update_client_status(db: Session, client_uuid: str, status: ClientStatusEnum, error_message: Optional[str] = None) -> Optional[Client]:
        client = ClientService.get_client_by_uuid(db, client_uuid)
        if client:
            client.status = status
            if error_message:
                client.error_message = error_message
            db.commit()
            db.refresh(client)
            logger.debug(f"Updated client {client_uuid} status to {status.value}")
        return client
    
    @staticmethod
    def update_client_outputs(db: Session, client_uuid: str, outputs: dict) -> Optional[Client]:
        client = ClientService.get_client_by_uuid(db, client_uuid)
        if client:
            safe_outputs = {k: v for k, v in outputs.items() if k not in ['db_password', 'database_init_script']}
            client.terraform_outputs = json.dumps(safe_outputs)
            db.commit()
            db.refresh(client)
            logger.debug(f"Updated terraform outputs for client {client_uuid}")
        return client
    
    @staticmethod
    def parse_terraform_outputs(outputs_json: Optional[str]) -> Optional[TerraformOutputs]:
        if not outputs_json:
            return None
        try:
            outputs_dict = json.loads(outputs_json)
            return TerraformOutputs(**outputs_dict)
        except Exception as e:
            logger.warning(f"Failed to parse terraform outputs: {e}")
            return None
    
    @staticmethod
    def map_db_status_to_api_status(db_status: ClientStatusEnum) -> ClientStatus:
        mapping = {
            ClientStatusEnum.PENDING: ClientStatus.PENDING,
            ClientStatusEnum.IN_PROGRESS: ClientStatus.IN_PROGRESS,
            ClientStatusEnum.COMPLETED: ClientStatus.COMPLETED,
            ClientStatusEnum.FAILED: ClientStatus.FAILED,
        }
        return mapping.get(db_status, ClientStatus.PENDING)
