"""
Terraform orchestration service for managing client infrastructure deployments.
"""
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from src.config.settings import settings

logger = logging.getLogger(__name__)


class TerraformService:
    """Service for managing Terraform operations."""
    
    def __init__(self):
        self.template_path = settings.terraform_template_path
        self.deployments_path = settings.deployments_base_path
        self.terraform_binary = settings.terraform_binary
        
    def create_client_workspace(self, client_uuid: str, client_info: Dict[str, Any]) -> Path:
        """
        Create isolated workspace for a client by copying template files.
        
        Args:
            client_uuid: Unique identifier for the client
            client_info: Client information including name, environment, region
            
        Returns:
            Path to the created workspace
        """
        workspace_path = self.deployments_path / client_uuid
        
        if workspace_path.exists():
            raise ValueError(f"Workspace already exists for client {client_uuid}")
        
        workspace_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created workspace directory: {workspace_path}")
        
        for item in self.template_path.iterdir():
            if item.is_file() and not item.name.endswith('.template'):
                shutil.copy2(item, workspace_path)
                logger.debug(f"Copied {item.name} to workspace")
            elif item.is_dir() and item.name in ["sql", "scripts"]:
                shutil.copytree(item, workspace_path / item.name)
                logger.debug(f"Copied {item.name} directory to workspace")
        
        credentials_src = Path("/app") / settings.gcp_credentials_file
        if not credentials_src.exists():
            credentials_src = settings.base_dir / settings.gcp_credentials_file
        
        if credentials_src.exists():
            shutil.copy2(credentials_src, workspace_path / settings.gcp_credentials_file)
            logger.debug(f"Copied GCP credentials to workspace from {credentials_src}")
        else:
            logger.warning(f"GCP credentials file not found at {credentials_src}")
        
        self.generate_tfvars(workspace_path, client_uuid, client_info)
        self.generate_backend_config(workspace_path, client_uuid)
        
        return workspace_path
    
    def generate_tfvars(self, workspace_path: Path, client_uuid: str, client_info: Dict[str, Any]) -> None:
        """
        Generate terraform.tfvars file with minimal required values.
        All naming and configuration is handled by Terraform locals and defaults.
        
        Args:
            workspace_path: Path to the client workspace
            client_uuid: Unique identifier for the client
            client_info: Client information
        """
        current_date = datetime.now().strftime("%Y-%m-%d")
        environment = client_info.get('environment', 'dev')
        
        tfvars_content = f"""project_id   = "{settings.gcp_project_id}"
region       = "{client_info.get('region', settings.gcp_region)}"
environment  = "{environment}"
cluster_uuid = "{client_uuid}"
created_date = "{current_date}"
"""
        
        tfvars_path = workspace_path / "terraform.tfvars"
        tfvars_path.write_text(tfvars_content)
        logger.info(f"Generated terraform.tfvars: {tfvars_path}")
    
    def generate_backend_config(self, workspace_path: Path, client_uuid: str) -> None:
        """
        Generate backend.tf file for GCS state storage.
        
        Args:
            workspace_path: Path to the client workspace
            client_uuid: Unique identifier for the client
        """
        client_uuid_underscore = client_uuid.replace('-', '_')
        backend_content = f"""terraform {{
  backend "gcs" {{
    bucket = "{settings.state_bucket_name}"
    prefix = "{client_uuid_underscore}"
  }}
}}
"""
        
        backend_path = workspace_path / "backend.tf"
        backend_path.write_text(backend_content)
        logger.info(f"Generated backend.tf for client {client_uuid} - state will be stored in GCS bucket '{settings.state_bucket_name}' with prefix: {client_uuid_underscore}")
    
    def run_terraform_init(self, workspace_path: Path) -> Tuple[bool, str]:
        """
        Initialize Terraform in the workspace.
        
        Args:
            workspace_path: Path to the client workspace
            
        Returns:
            Tuple of (success, output)
        """
        logger.info(f"Running terraform init in {workspace_path}")
        
        credentials_file = workspace_path / settings.gcp_credentials_file
        if not credentials_file.exists():
            credentials_src = Path("/app") / settings.gcp_credentials_file
            if not credentials_src.exists():
                credentials_src = settings.base_dir / settings.gcp_credentials_file
            
            if credentials_src.exists():
                shutil.copy2(credentials_src, credentials_file)
                logger.info(f"Copied credentials to workspace: {credentials_file}")
            else:
                return False, f"GCP credentials file not found: {settings.gcp_credentials_file}"
        
        env = os.environ.copy()
        env['GOOGLE_APPLICATION_CREDENTIALS'] = str(credentials_file)
        
        try:
            result = subprocess.run(
                [self.terraform_binary, "init", "-no-color"],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=settings.terraform_init_timeout,
                env=env
            )
            
            log_path = workspace_path / "init.log"
            log_path.write_text(result.stdout + "\n" + result.stderr)
            
            if result.returncode == 0:
                logger.info("Terraform init completed successfully")
                return True, result.stdout
            else:
                logger.error(f"Terraform init failed: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            error_msg = f"Terraform init timed out after {settings.terraform_init_timeout} seconds"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Error running terraform init: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def run_terraform_apply(self, workspace_path: Path) -> Tuple[bool, str]:
        """
        Apply Terraform configuration.
        
        Args:
            workspace_path: Path to the client workspace
            
        Returns:
            Tuple of (success, output)
        """
        logger.info(f"Running terraform apply in {workspace_path}")
        
        credentials_file = workspace_path / settings.gcp_credentials_file
        if not credentials_file.exists():
            credentials_src = Path("/app") / settings.gcp_credentials_file
            if not credentials_src.exists():
                credentials_src = settings.base_dir / settings.gcp_credentials_file
            
            if credentials_src.exists():
                shutil.copy2(credentials_src, credentials_file)
                logger.info(f"Copied credentials to workspace: {credentials_file}")
            else:
                return False, f"GCP credentials file not found: {settings.gcp_credentials_file}"
        
        env = os.environ.copy()
        env['GOOGLE_APPLICATION_CREDENTIALS'] = str(credentials_file)
        
        try:
            result = subprocess.run(
                [self.terraform_binary, "apply", "-auto-approve", "-no-color"],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=settings.terraform_apply_timeout,
                env=env
            )
            
            log_path = workspace_path / "apply.log"
            log_path.write_text(result.stdout + "\n" + result.stderr)
            
            if result.returncode == 0:
                logger.info("Terraform apply completed successfully")
                return True, result.stdout
            else:
                logger.error(f"Terraform apply failed: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            error_msg = f"Terraform apply timed out after {settings.terraform_apply_timeout} seconds"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Error running terraform apply: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def get_terraform_outputs(self, workspace_path: Path) -> Optional[Dict[str, Any]]:
        """
        Get Terraform outputs after successful apply.
        
        Args:
            workspace_path: Path to the client workspace
            
        Returns:
            Dictionary of outputs or None if failed
        """
        logger.info(f"Getting terraform outputs from {workspace_path}")
        
        credentials_file = workspace_path / settings.gcp_credentials_file
        if credentials_file.exists():
            env = os.environ.copy()
            env['GOOGLE_APPLICATION_CREDENTIALS'] = str(credentials_file)
        else:
            env = os.environ.copy()
        
        try:
            result = subprocess.run(
                [self.terraform_binary, "output", "-json"],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=60,
                env=env
            )
            
            if result.returncode == 0:
                outputs_raw = json.loads(result.stdout)
                outputs = {}
                for key, value in outputs_raw.items():
                    if isinstance(value, dict) and 'value' in value:
                        outputs[key] = value['value']
                    else:
                        outputs[key] = value
                
                logger.info(f"Retrieved {len(outputs)} outputs")
                return outputs
            else:
                logger.error(f"Failed to get outputs: {result.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting terraform outputs: {str(e)}")
            return None
    
    def run_full_deployment(self, client_uuid: str, client_info: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Run complete deployment process: workspace creation, init, apply, and get outputs.
        
        Args:
            client_uuid: Unique identifier for the client
            client_info: Client information
            
        Returns:
            Tuple of (success, outputs, error_message)
        """
        try:
            # Create workspace
            workspace_path = self.create_client_workspace(client_uuid, client_info)
            
            # Run terraform init
            success, output = self.run_terraform_init(workspace_path)
            if not success:
                return False, None, f"Terraform init failed: {output}"
            
            # Run terraform apply
            success, output = self.run_terraform_apply(workspace_path)
            if not success:
                return False, None, f"Terraform apply failed: {output}"
            
            # Get outputs
            outputs = self.get_terraform_outputs(workspace_path)
            if outputs is None:
                return False, None, "Failed to retrieve Terraform outputs"
            
            return True, outputs, None
            
        except Exception as e:
            error_msg = f"Deployment failed: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg
    
    def workspace_exists(self, client_uuid: str) -> bool:
        """Check if workspace exists for a client."""
        workspace_path = self.deployments_path / client_uuid
        return workspace_path.exists()
    
    def get_workspace_path(self, client_uuid: str) -> Path:
        """Get the workspace path for a client."""
        return self.deployments_path / client_uuid
    
    def run_terraform_destroy(self, workspace_path: Path) -> Tuple[bool, str]:
        """
        Destroy Terraform-managed infrastructure.
        
        Args:
            workspace_path: Path to the client workspace
            
        Returns:
            Tuple of (success, output)
        """
        logger.info(f"Running terraform destroy in {workspace_path}")
        
        if not workspace_path.exists():
            logger.warning(f"Workspace does not exist: {workspace_path}")
            return False, "Workspace not found"
        
        # Ensure credentials file exists
        credentials_file = workspace_path / settings.gcp_credentials_file
        if not credentials_file.exists():
            # Try to copy credentials if missing
            credentials_src = Path("/app") / settings.gcp_credentials_file
            if not credentials_src.exists():
                credentials_src = settings.base_dir / settings.gcp_credentials_file
            
            if credentials_src.exists():
                shutil.copy2(credentials_src, credentials_file)
                logger.info(f"Copied credentials to workspace: {credentials_file}")
            else:
                return False, f"GCP credentials file not found: {settings.gcp_credentials_file}"
        
        # Set environment variable for GCP credentials
        env = os.environ.copy()
        env['GOOGLE_APPLICATION_CREDENTIALS'] = str(credentials_file)
        
        try:
            result = subprocess.run(
                [self.terraform_binary, "destroy", "-auto-approve", "-no-color"],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=settings.terraform_apply_timeout,  # Use same timeout as apply
                env=env
            )
            
            # Save output to log file
            log_path = workspace_path / "destroy.log"
            log_path.write_text(result.stdout + "\n" + result.stderr)
            
            if result.returncode == 0:
                logger.info("Terraform destroy completed successfully")
                return True, result.stdout
            else:
                logger.error(f"Terraform destroy failed: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            error_msg = f"Terraform destroy timed out after {settings.terraform_apply_timeout} seconds"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Error running terraform destroy: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def destroy_client_infrastructure(self, client_uuid: str) -> Tuple[bool, Optional[str]]:
        """
        Destroy all infrastructure for a client.
        
        Args:
            client_uuid: Unique identifier for the client
            
        Returns:
            Tuple of (success, error_message)
        """
        workspace_path = self.get_workspace_path(client_uuid)
        
        if not workspace_path.exists():
            logger.warning(f"Workspace not found for client {client_uuid}")
            return True, None  # Consider it successful if workspace doesn't exist
        
        # Run terraform destroy
        success, output = self.run_terraform_destroy(workspace_path)
        
        if success:
            # Optionally clean up workspace directory after successful destroy
            # Keep it for now to preserve logs
            logger.info(f"Infrastructure destroyed for client {client_uuid}")
            return True, None
        else:
            return False, f"Terraform destroy failed: {output}"

