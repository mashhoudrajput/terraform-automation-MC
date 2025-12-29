from datetime import datetime
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field


class ClientStatus(str, Enum):
    """Client deployment status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ClientRegistrationRequest(BaseModel):
    """Request model for client registration."""
    client_name: str = Field(..., min_length=1, max_length=100, description="Name of the client organization")
    client_uuid: str = Field(..., description="UUID for the client (provided by frontend)")
    environment: str = Field(default="dev", pattern="^(dev|staging|prod)$", description="Deployment environment")
    region: str = Field(default="me-central2", description="GCP region for deployment")
    parent_uuid: Optional[str] = Field(default=None, description="Parent hospital UUID for sub-hospitals")
    
    class Config:
        json_schema_extra = {
            "example": {
                "client_name": "Acme Corp",
                "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
                "environment": "dev",
                "region": "me-central2",
                "parent_uuid": None
            }
        }


class ClientRegistrationResponse(BaseModel):
    """Response model after client registration."""
    client_uuid: str = Field(..., description="Unique identifier for the client")
    job_id: str = Field(..., description="Job identifier for tracking deployment")
    status: ClientStatus = Field(..., description="Current deployment status")
    status_url: str = Field(..., description="URL to check deployment status")
    created_at: datetime = Field(..., description="Timestamp of registration")
    
    class Config:
        json_schema_extra = {
            "example": {
                "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
                "job_id": "job-550e8400",
                "status": "in_progress",
                "status_url": "/api/clients/550e8400-e29b-41d4-a716-446655440000/status",
                "created_at": "2025-11-25T10:30:00Z"
            }
        }


class TerraformOutputs(BaseModel):
    """Terraform deployment outputs."""
    db_instance_name: Optional[str] = None
    db_private_ip: Optional[str] = None
    db_port: Optional[str] = None
    database_name: Optional[str] = None
    db_username: Optional[str] = None
    connection_uri: Optional[str] = None
    private_bucket_name: Optional[str] = None
    public_bucket_name: Optional[str] = None
    secret_name: Optional[str] = None
    cluster_id: Optional[str] = None
    environment: Optional[str] = None
    deployment_region: Optional[str] = None


class ClientStatusResponse(BaseModel):
    """Response model for client status query."""
    client_uuid: str
    client_name: str
    job_id: str
    status: ClientStatus
    environment: str
    region: str
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None
    terraform_outputs: Optional[TerraformOutputs] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
                "client_name": "Acme Corp",
                "job_id": "job-550e8400",
                "status": "completed",
                "environment": "dev",
                "region": "me-central2",
                "created_at": "2025-11-25T10:30:00Z",
                "updated_at": "2025-11-25T10:45:00Z",
                "error_message": None,
                "terraform_outputs": {
                    "db_instance_name": "mysql-instance-dev",
                    "db_private_ip": "10.7.1.9",
                    "db_port": "3306",
                    "database_name": "myapp_db",
                    "db_username": "root"
                }
            }
        }


class ClientListItem(BaseModel):
    """Model for client in list response."""
    client_uuid: str
    client_name: str
    status: ClientStatus
    environment: str
    region: str
    parent_uuid: Optional[str] = None
    created_at: datetime


class ClientListResponse(BaseModel):
    """Response model for client list."""
    clients: list[ClientListItem]
    total: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "clients": [
                    {
                        "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
                        "client_name": "Acme Corp",
                        "status": "completed",
                        "environment": "dev",
                        "region": "me-central2",
                        "created_at": "2025-11-25T10:30:00Z"
                    }
                ],
                "total": 1
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

