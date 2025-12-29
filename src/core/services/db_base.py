import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple
from urllib.parse import urlparse, unquote
from google.cloud import secretmanager
from google.cloud import storage
from google.oauth2 import service_account
from src.config.settings import settings


class BaseDatabaseService:
    def __init__(self):
        self._secret_client = None
        self.project_id = settings.gcp_project_id
    
    @property
    def secret_client(self):
        if self._secret_client is None:
            credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            if not credentials_path:
                for path in [Path("/app/terraform-sa.json"), Path("/app") / settings.gcp_credentials_file, settings.base_dir / settings.gcp_credentials_file]:
                    if path.exists():
                        credentials_path = str(path)
                        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
                        break
            
            if credentials_path and Path(credentials_path).exists():
                credentials = service_account.Credentials.from_service_account_file(credentials_path)
                self._secret_client = secretmanager.SecretManagerServiceClient(credentials=credentials)
            else:
                self._secret_client = secretmanager.SecretManagerServiceClient()
        return self._secret_client
    
    def parse_connection_uri(self, connection_uri: str) -> dict:
        parsed = urlparse(connection_uri)
        return {
            'user': unquote(parsed.username) if parsed.username else '',
            'password': unquote(parsed.password) if parsed.password else '',
            'host': parsed.hostname if parsed.hostname else '',
            'port': parsed.port if parsed.port else 3306,
            'database': unquote(parsed.path.lstrip('/')).split('?')[0] if parsed.path else ''
        }
    
    def get_connection_uri_from_secret(self, secret_name: str) -> str:
        secret_path = f"projects/{self.project_id}/secrets/{secret_name}/versions/latest"
        response = self.secret_client.access_secret_version(request={"name": secret_path})
        return response.payload.data.decode("UTF-8")
    
    def upload_sql_to_bucket(self, bucket_name: str, client_uuid: str, sql_content: str, sql_filename: str = "cluster_hospitals.sql") -> Tuple[bool, str]:
        try:
            storage_client = storage.Client(project=settings.gcp_project_id)
            bucket = storage_client.bucket(bucket_name)
            blob_path = f"database-init/{client_uuid}/{sql_filename}"
            blob = bucket.blob(blob_path)
            blob.upload_from_string(sql_content, content_type='text/plain')
            return True, f"gs://{bucket_name}/{blob_path}"
        except Exception as e:
            return False, str(e)
    
    def sanitize_db_name(self, name: str) -> str:
        db_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name.lower())
        db_name = re.sub(r'_+', '_', db_name).strip('_')
        return db_name if db_name else f"db_{name[:8]}"
    
    def escape_password_for_shell(self, password: str) -> str:
        return password.replace("'", "'\\''")

    def generate_temp_ssh_key(self, env: dict) -> Tuple[Path, Path]:
        tmp_dir = Path(tempfile.mkdtemp())
        priv = tmp_dir / "task_key"
        pub = tmp_dir / "task_key.pub"
        subprocess.run(
            ["ssh-keygen", "-t", "rsa", "-f", str(priv), "-N", "", "-q"],
            check=True,
            env=env,
        )
        return priv, pub

    def cleanup_os_login_key(self, env: dict, key_path: Path) -> None:
        if not key_path:
            return
        try:
            if key_path.exists():
                subprocess.run(
                    [
                        "gcloud",
                        "compute",
                        "os-login",
                        "ssh-keys",
                        "remove",
                        f"--key-file={key_path}",
                        "--quiet",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=env,
                    check=False,
                )
        except Exception:
            pass

    def cleanup_local_key_files(self, priv: Path, pub: Path) -> None:
        try:
            if priv:
                priv.unlink(missing_ok=True)
            if pub:
                pub.unlink(missing_ok=True)
            if pub and pub.parent.exists():
                shutil.rmtree(pub.parent, ignore_errors=True)
        except Exception:
            pass

