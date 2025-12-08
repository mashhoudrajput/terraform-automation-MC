import os
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple
from src.core.services.db_base import BaseDatabaseService
from src.config.settings import settings


class MainHospitalDBService(BaseDatabaseService):
    def create_tables(self, client_uuid: str, region: str, private_bucket_name: str) -> Tuple[bool, str]:
        try:
            region = region or settings.gcp_region
            vm_zone = settings.db_init_vm_zone or f"{region}-a"
            
            if not private_bucket_name:
                return False, "Private bucket name is required"
            
            secret_name = f"{client_uuid.replace('-', '_')}_DATABASE_URI"
            connection_uri = self.get_connection_uri_from_secret(secret_name)
            conn_info = self.parse_connection_uri(connection_uri)
            
            sql_filename = "cluster_hospitals.sql"
            sql_file_path = Path(f"/app/infrastructure/base/sql/{sql_filename}")
            if not sql_file_path.exists():
                sql_file_path = settings.base_dir / "infrastructure" / "base" / "sql" / sql_filename
            
            if not sql_file_path.exists():
                return False, f"{sql_filename} file not found"
            
            sql_content = sql_file_path.read_text(encoding='utf-8')
            
            upload_success, gcs_path = self.upload_sql_to_bucket(private_bucket_name, client_uuid, sql_content, sql_filename)
            if not upload_success:
                return False, f"Failed to upload SQL file: {gcs_path}"
            
            escaped_password = self.escape_password_for_shell(conn_info['password'])
            script_content = self._generate_script(conn_info, escaped_password, gcs_path, client_uuid, sql_filename)
            
            env = os.environ.copy()
            env['GOOGLE_APPLICATION_CREDENTIALS'] = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '/app/terraform-sa.json')
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as tmp_script:
                tmp_script.write(script_content)
                tmp_script_path = tmp_script.name
                os.chmod(tmp_script_path, 0o755)
            
            try:
                scp_cmd = [
                    'gcloud', 'compute', 'scp',
                    tmp_script_path,
                    f'{settings.db_init_vm_name}:/tmp/create_tables_{client_uuid}.sh',
                    '--zone', vm_zone,
                    '--project', settings.gcp_project_id,
                    '--quiet'
                ]
                
                scp_result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=60, env=env)
                if scp_result.returncode != 0:
                    return False, f"Failed to copy script to VM: {scp_result.stderr}"
                
                ssh_cmd = [
                    'gcloud', 'compute', 'ssh', settings.db_init_vm_name,
                    '--zone', vm_zone,
                    '--project', settings.gcp_project_id,
                    '--command', f'sudo bash /tmp/create_tables_{client_uuid}.sh'
                ]
                
                result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=600, env=env)
                
                if result.returncode == 0:
                    return True, "Tables created successfully"
                else:
                    output = f"{result.stdout}\n{result.stderr}".strip()
                    return False, f"Failed to create tables: {output[:500]}"
            finally:
                try:
                    os.unlink(tmp_script_path)
                except:
                    pass
        except subprocess.TimeoutExpired:
            return False, "Table creation timed out after 10 minutes"
        except Exception as e:
            return False, f"Failed to create tables: {str(e)}"
    
    def _generate_script(self, conn_info: dict, escaped_password: str, gcs_path: str, client_uuid: str, sql_filename: str) -> str:
        return f"""#!/bin/bash
set -e
echo "Starting table creation process"
echo "Timestamp: $(date)"

echo "Step 1: Testing VM connectivity..."
PUBLIC_IP=$(curl -s ifconfig.io 2>/dev/null || echo "N/A")
echo "VM Public IP: $PUBLIC_IP"

echo "Step 2: Checking MySQL client..."
if ! command -v mysql &> /dev/null; then
    echo "Installing MySQL client..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq mysql-client
    elif command -v yum &> /dev/null; then
        sudo yum install -y -q mysql
    else
        echo "ERROR: Cannot install MySQL client"
        exit 1
    fi
fi

echo "Step 3: Checking gsutil..."
if ! command -v gsutil &> /dev/null; then
    echo "Installing gsutil..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq gsutil
    elif command -v yum &> /dev/null; then
        sudo yum install -y -q gcloud-sdk
    else
        echo "ERROR: Cannot install gsutil"
        exit 1
    fi
fi

echo "Step 4: Downloading SQL file from GCS..."
echo "Source: {gcs_path}"
if gsutil cp {gcs_path} /tmp/create_tables_{client_uuid}.sql; then
    echo "SQL file downloaded successfully"
else
    echo "ERROR: Failed to download SQL file from GCS"
    exit 1
fi

echo "Step 5: Testing database connection..."
if timeout 30 mysql -h {conn_info['host']} -P {conn_info['port']} -u {conn_info['user']} -p'{escaped_password}' --connect-timeout=10 -e "SELECT 1 as connection_test;" {conn_info['database']} 2>&1; then
    echo "Database connection successful"
else
    echo "ERROR: Failed to connect to database"
    rm -f /tmp/create_tables_{client_uuid}.sql
    exit 1
fi

echo "Step 6: Executing SQL statements..."
timeout 540 mysql -h {conn_info['host']} -P {conn_info['port']} -u {conn_info['user']} -p'{escaped_password}' --connect-timeout=10 {conn_info['database']} < /tmp/create_tables_{client_uuid}.sql 2>&1

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "Tables created successfully"
    rm -f /tmp/create_tables_{client_uuid}.sql
    exit 0
else
    echo "ERROR: Failed to create tables (exit code: $EXIT_CODE)"
    rm -f /tmp/create_tables_{client_uuid}.sql
    exit 1
fi
"""

