"""
Configuration settings for the multi-client Terraform backend.
"""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # API Configuration
    api_title: str = "Multi-Client Terraform Provisioning API"
    api_version: str = "1.0.0"
    api_description: str = "API for provisioning isolated GCP infrastructure per client"
    
    # Paths
    base_dir: Path = Path(__file__).parent.parent.parent.resolve()
    terraform_template_path: Path = Path("/app/infrastructure/base")
    deployments_base_path: Path = Path("/data/deployments")
    database_path: Path = Path("/data/clients.db")
    
    # GCP Configuration
    gcp_credentials_file: str = "terraform-sa.json"
    gcp_project_id: str = "lively-synapse-400818"
    gcp_region: str = "me-central2"
    
    # Terraform Configuration
    terraform_binary: str = "terraform"
    terraform_init_timeout: int = 300  # seconds
    terraform_apply_timeout: int = 1800  # 30 minutes
    
    # Backend Type
    state_backend_type: str = "gcs"  # "local" or "gcs"
    state_bucket_name: str = "medical-circles-terraform-state-files"
    
    # Database Configuration
    database_url: str = f"sqlite:///{database_path}"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()

# Ensure deployment directories exist
settings.deployments_base_path.mkdir(parents=True, exist_ok=True)

