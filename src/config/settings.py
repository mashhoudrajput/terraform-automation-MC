import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    api_title: str = "Multi-Client Terraform Provisioning API"
    api_version: str = "1.0.0"
    api_description: str = "API for provisioning isolated GCP infrastructure per client"
    api_key: Optional[str] = Field(default=None, description="API key for authentication (set via API_KEY env var)")
    
    base_dir: Path = Path(__file__).parent.parent.parent.resolve()
    terraform_template_path: Path = Path("/app/infrastructure/base")
    deployments_base_path: Path = Path("/data/deployments")
    database_path: Path = Path("/data/clients.db")
    
    gcp_credentials_file: str = "terraform-sa.json"
    gcp_project_id: str = "lively-synapse-400818"
    gcp_region: str = "me-central2"
    
    terraform_binary: str = "terraform"
    terraform_init_timeout: int = 600
    terraform_apply_timeout: int = 1800
    
    state_backend_type: str = "gcs"
    state_bucket_name: str = "medical-circles-terraform-state-files"
    
    database_url: str = f"sqlite:///{database_path}"
    database_backup_bucket: Optional[str] = "medical-circles-terraform-state-files"
    database_backup_object: str = "clients.db"
    database_backup_interval_seconds: int = 300

    serve_frontend: bool = False
    
    db_init_vm_name: str = "db-init-cluster-001-dev"
    db_init_vm_zone: str = "me-central2-a"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
settings.deployments_base_path.mkdir(parents=True, exist_ok=True)
