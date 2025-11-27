"""
Client management service for database operations.
"""
import json
import logging
from typing import Optional, List
from uuid import uuid4
from sqlalchemy.orm import Session

from src.core.database import Client, ClientStatusEnum
from src.models.models import (
    ClientRegistrationRequest,
    ClientStatus,
    TerraformOutputs
)

logger = logging.getLogger(__name__)


class ClientService:
    """Service for managing client records in the database."""
    
    @staticmethod
    def create_client(db: Session, request: ClientRegistrationRequest) -> Client:
        """
        Create a new client record in the database.
        
        Args:
            db: Database session
            request: Client registration request
            
        Returns:
            Created client record
        """
        client_uuid = str(uuid4())
        job_id = f"job-{client_uuid[:8]}"
        
        client = Client(
            uuid=client_uuid,
            client_name=request.client_name,
            job_id=job_id,
            status=ClientStatusEnum.PENDING,
            environment=request.environment,
            region=request.region,
            terraform_outputs=None,
            error_message=None
        )
        
        db.add(client)
        db.commit()
        db.refresh(client)
        
        logger.info(f"Created client record: {client_uuid} ({request.client_name})")
        return client
    
    @staticmethod
    def get_client_by_uuid(db: Session, client_uuid: str) -> Optional[Client]:
        """Get client by UUID."""
        return db.query(Client).filter(Client.uuid == client_uuid).first()
    
    @staticmethod
    def get_client_by_job_id(db: Session, job_id: str) -> Optional[Client]:
        """Get client by job ID."""
        return db.query(Client).filter(Client.job_id == job_id).first()
    
    @staticmethod
    def get_all_clients(db: Session) -> List[Client]:
        """Get all clients ordered by creation date."""
        return db.query(Client).order_by(Client.created_at.desc()).all()
    
    @staticmethod
    def update_client_status(
        db: Session,
        client_uuid: str,
        status: ClientStatusEnum,
        error_message: Optional[str] = None
    ) -> Optional[Client]:
        """
        Update client status.
        
        Args:
            db: Database session
            client_uuid: Client UUID
            status: New status
            error_message: Optional error message if status is FAILED
            
        Returns:
            Updated client or None if not found
        """
        client = ClientService.get_client_by_uuid(db, client_uuid)
        if client:
            client.status = status
            if error_message:
                client.error_message = error_message
            db.commit()
            db.refresh(client)
            logger.info(f"Updated client {client_uuid} status to {status.value}")
        return client
    
    @staticmethod
    def update_client_outputs(
        db: Session,
        client_uuid: str,
        outputs: dict
    ) -> Optional[Client]:
        """
        Update client with Terraform outputs.
        
        Args:
            db: Database session
            client_uuid: Client UUID
            outputs: Terraform outputs dictionary
            
        Returns:
            Updated client or None if not found
        """
        client = ClientService.get_client_by_uuid(db, client_uuid)
        if client:
            # Filter sensitive outputs before storing
            safe_outputs = {k: v for k, v in outputs.items() if k not in ['db_password', 'database_init_script']}
            client.terraform_outputs = json.dumps(safe_outputs)
            db.commit()
            db.refresh(client)
            logger.info(f"Updated client {client_uuid} with Terraform outputs")
        return client
    
    @staticmethod
    def parse_terraform_outputs(outputs_json: Optional[str]) -> Optional[TerraformOutputs]:
        """
        Parse stored JSON outputs into TerraformOutputs model.
        
        Args:
            outputs_json: JSON string of outputs
            
        Returns:
            TerraformOutputs model or None
        """
        if not outputs_json:
            return None
        
        try:
            outputs_dict = json.loads(outputs_json)
            return TerraformOutputs(**outputs_dict)
        except Exception as e:
            logger.error(f"Error parsing outputs: {e}")
            return None
    
    @staticmethod
    def map_db_status_to_api_status(db_status: ClientStatusEnum) -> ClientStatus:
        """Map database status enum to API status enum."""
        mapping = {
            ClientStatusEnum.PENDING: ClientStatus.PENDING,
            ClientStatusEnum.IN_PROGRESS: ClientStatus.IN_PROGRESS,
            ClientStatusEnum.COMPLETED: ClientStatus.COMPLETED,
            ClientStatusEnum.FAILED: ClientStatus.FAILED,
        }
        return mapping.get(db_status, ClientStatus.PENDING)

