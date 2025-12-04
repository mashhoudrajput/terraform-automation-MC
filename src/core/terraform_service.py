import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from src.config.settings import settings


class TerraformService:
    def __init__(self):
        self.template_path = settings.terraform_template_path
        self.deployments_path = settings.deployments_base_path
        self.terraform_binary = settings.terraform_binary
        
    def create_client_workspace(self, client_uuid: str, client_info: Dict[str, Any]) -> Path:
        workspace_path = self.deployments_path / client_uuid
        
        if workspace_path.exists():
            try:
                shutil.rmtree(workspace_path)
            except Exception as e:
                raise ValueError(f"Workspace already exists for client {client_uuid} and could not be cleaned up: {e}")
        
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        for item in self.template_path.iterdir():
            if item.is_file() and not item.name.endswith('.template'):
                shutil.copy2(item, workspace_path)
        
        credentials_src = Path("/app") / settings.gcp_credentials_file
        if not credentials_src.exists():
            credentials_src = settings.base_dir / settings.gcp_credentials_file
        
        if credentials_src.exists():
            shutil.copy2(credentials_src, workspace_path / settings.gcp_credentials_file)
        
        self.generate_tfvars(workspace_path, client_uuid, client_info)
        self.generate_backend_config(workspace_path, client_uuid)
        return workspace_path
    
    def generate_tfvars(self, workspace_path: Path, client_uuid: str, client_info: Dict[str, Any]) -> None:
        current_date = datetime.now().strftime("%Y-%m-%d")
        environment = client_info.get('environment', 'dev')
        is_sub_hospital = client_info.get('parent_uuid') is not None
        parent_instance_name = ""
        hospital_name = client_info.get('client_name', '')
        
        if is_sub_hospital:
            parent_uuid = client_info.get('parent_uuid')
            parent_instance_name = f"mc-cluster-{parent_uuid.replace('_', '-')}"
        
        tfvars_content = f"""project_id   = "{settings.gcp_project_id}"
region       = "{client_info.get('region', settings.gcp_region)}"
environment  = "{environment}"
cluster_uuid = "{client_uuid}"
created_date = "{current_date}"
is_sub_hospital = {str(is_sub_hospital).lower()}
parent_instance_name = "{parent_instance_name}"
hospital_name = "{hospital_name}"
"""
        tfvars_path = workspace_path / "terraform.tfvars"
        tfvars_path.write_text(tfvars_content)
    
    def generate_backend_config(self, workspace_path: Path, client_uuid: str) -> None:
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
    
    def run_terraform_init(self, workspace_path: Path) -> Tuple[bool, str]:
        credentials_file = workspace_path / settings.gcp_credentials_file
        if not credentials_file.exists():
            credentials_src = Path("/app") / settings.gcp_credentials_file
            if not credentials_src.exists():
                credentials_src = settings.base_dir / settings.gcp_credentials_file
            if credentials_src.exists():
                shutil.copy2(credentials_src, credentials_file)
            else:
                return False, f"GCP credentials file not found: {settings.gcp_credentials_file}"
        
        env = os.environ.copy()
        env['GOOGLE_APPLICATION_CREDENTIALS'] = str(credentials_file)
        
        try:
            result = subprocess.run(
                [self.terraform_binary, "init", "-no-color", "-upgrade"],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=settings.terraform_init_timeout,
                env=env
            )
            log_path = workspace_path / "init.log"
            log_path.write_text(result.stdout + "\n" + result.stderr)
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr or result.stdout
        except subprocess.TimeoutExpired:
            return False, f"Terraform init timed out after {settings.terraform_init_timeout} seconds"
        except Exception as e:
            return False, f"Error running terraform init: {str(e)}"
    
    def run_terraform_apply(self, workspace_path: Path) -> Tuple[bool, str]:
        credentials_file = workspace_path / settings.gcp_credentials_file
        if not credentials_file.exists():
            credentials_src = Path("/app") / settings.gcp_credentials_file
            if not credentials_src.exists():
                credentials_src = settings.base_dir / settings.gcp_credentials_file
            if credentials_src.exists():
                shutil.copy2(credentials_src, credentials_file)
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
                return True, result.stdout
            else:
                return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, f"Terraform apply timed out after {settings.terraform_apply_timeout} seconds"
        except Exception as e:
            return False, f"Error running terraform apply: {str(e)}"
    
    def get_terraform_outputs(self, workspace_path: Path) -> Optional[Dict[str, Any]]:
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
                return outputs
            else:
                return None
        except Exception:
            return None
    
    def run_full_deployment(self, client_uuid: str, client_info: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        try:
            workspace_path = self.create_client_workspace(client_uuid, client_info)
            success, output = self.run_terraform_init(workspace_path)
            if not success:
                return False, None, f"Terraform init failed: {output}"
            success, output = self.run_terraform_apply(workspace_path)
            if not success:
                return False, None, f"Terraform apply failed: {output}"
            outputs = self.get_terraform_outputs(workspace_path)
            if outputs is None:
                return False, None, "Failed to retrieve Terraform outputs"
            return True, outputs, None
        except Exception as e:
            return False, None, f"Deployment failed: {str(e)}"
    
    def workspace_exists(self, client_uuid: str) -> bool:
        workspace_path = self.deployments_path / client_uuid
        return workspace_path.exists()
    
    def get_workspace_path(self, client_uuid: str) -> Path:
        return self.deployments_path / client_uuid
    
    def run_terraform_destroy(self, workspace_path: Path) -> Tuple[bool, str]:
        if not workspace_path.exists():
            return False, "Workspace not found"
        
        credentials_file = workspace_path / settings.gcp_credentials_file
        if not credentials_file.exists():
            credentials_src = Path("/app") / settings.gcp_credentials_file
            if not credentials_src.exists():
                credentials_src = settings.base_dir / settings.gcp_credentials_file
            if credentials_src.exists():
                shutil.copy2(credentials_src, credentials_file)
            else:
                return False, f"GCP credentials file not found: {settings.gcp_credentials_file}"
        
        env = os.environ.copy()
        env['GOOGLE_APPLICATION_CREDENTIALS'] = str(credentials_file)
        
        try:
            result = subprocess.run(
                [self.terraform_binary, "destroy", "-auto-approve", "-no-color"],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=settings.terraform_apply_timeout,
                env=env
            )
            log_path = workspace_path / "destroy.log"
            log_path.write_text(result.stdout + "\n" + result.stderr)
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, f"Terraform destroy timed out after {settings.terraform_apply_timeout} seconds"
        except Exception as e:
            return False, f"Error running terraform destroy: {str(e)}"
    
    def destroy_client_infrastructure(self, client_uuid: str) -> Tuple[bool, Optional[str]]:
        workspace_path = self.get_workspace_path(client_uuid)
        if not workspace_path.exists():
            return True, None
        success, output = self.run_terraform_destroy(workspace_path)
        if success:
            return True, None
        else:
            return False, f"Terraform destroy failed: {output}"
