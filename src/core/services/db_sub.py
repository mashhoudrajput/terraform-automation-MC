import os
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple
from src.core.services.db_base import BaseDatabaseService
from src.config.settings import settings


class SubHospitalDBService(BaseDatabaseService):
    def create_database(self, parent_uuid: str, sub_hospital_name: str, sub_hospital_uuid: str, private_bucket_name: str, region: str = None) -> Tuple[bool, str]:
        try:
            region = region or settings.gcp_region
            vm_zone = settings.db_init_vm_zone or f"{region}-a"
            
            if not private_bucket_name:
                return False, "Private bucket name is required"
            
            parent_secret_name = f"{parent_uuid.replace('-', '_')}_DATABASE_URI"
            parent_connection_uri = self.get_connection_uri_from_secret(parent_secret_name)
            conn_info = self.parse_connection_uri(parent_connection_uri)
            
            db_name = self.sanitize_db_name(sub_hospital_name)
            if not db_name:
                db_name = f"sub_{sub_hospital_uuid[:8]}"
            
            escaped_password = self.escape_password_for_shell(conn_info['password'])
            mysql_command = f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            ssh_command = f"echo '{mysql_command}' | mysql -h {conn_info['host']} -P {conn_info['port']} -u {conn_info['user']} -p'{escaped_password}' mysql 2>&1 && echo 'SUCCESS: Database {db_name} created' || echo 'ERROR: Database creation failed'"
            
            env = os.environ.copy()
            env['GOOGLE_APPLICATION_CREDENTIALS'] = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '/app/terraform-sa.json')
            
            ssh_cmd = [
                'gcloud', 'compute', 'ssh', settings.db_init_vm_name,
                '--zone', vm_zone,
                '--project', settings.gcp_project_id,
                '--command', ssh_command,
                '--quiet'
            ]
            
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=120, env=env)
            
            output = (result.stdout or "").strip()
            error_output = (result.stderr or "").strip()
            combined_output = f"{output}\n{error_output}".strip()
            
            if result.returncode == 0 and 'SUCCESS' in output:
                sub_connection_uri = f"mysql://{conn_info['user']}:{conn_info['password']}@{conn_info['host']}:{conn_info['port']}/{db_name}"
                return True, sub_connection_uri
            else:
                return False, f"Failed to create database: {combined_output[:200]}"
        except subprocess.TimeoutExpired:
            return False, "Database creation timed out after 2 minutes"
        except Exception as e:
            return False, f"Failed to create sub-hospital database: {str(e)}"
    
    def create_tables(self, client_uuid: str, parent_uuid: str, database_name: str, region: str, private_bucket_name: str) -> Tuple[bool, str]:
        try:
            region = region or settings.gcp_region
            vm_zone = settings.db_init_vm_zone or f"{region}-a"
            
            if not private_bucket_name:
                return False, "Private bucket name is required"
            
            parent_secret_name = f"{parent_uuid.replace('-', '_')}_DATABASE_URI"
            connection_uri = self.get_connection_uri_from_secret(parent_secret_name)
            conn_info = self.parse_connection_uri(connection_uri)
            conn_info['database'] = database_name
            
            sql_filename = "subnetwork_hospitals.sql"
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

if ! command -v mysql &> /dev/null; then
    if command -v apt-get &> /dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y -qq mysql-client
    elif command -v yum &> /dev/null; then
        sudo yum install -y -q mysql
    else
        echo "ERROR: Cannot install MySQL client"
        exit 1
    fi
fi

if ! command -v gsutil &> /dev/null; then
    if command -v apt-get &> /dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y -qq gsutil
    elif command -v yum &> /dev/null; then
        sudo yum install -y -q gcloud-sdk
    else
        echo "ERROR: Cannot install gsutil"
        exit 1
    fi
fi

echo "Downloading SQL file from GCS..."
if ! gsutil cp {gcs_path} /tmp/create_tables_{client_uuid}.sql; then
    echo "ERROR: Failed to download SQL file from GCS"
    exit 1
fi

echo "Wrapping SQL to disable foreign key checks during import..."
echo "SET FOREIGN_KEY_CHECKS=0;" > /tmp/create_tables_{client_uuid}_wrapped.sql
cat /tmp/create_tables_{client_uuid}.sql >> /tmp/create_tables_{client_uuid}_wrapped.sql
echo "SET FOREIGN_KEY_CHECKS=1;" >> /tmp/create_tables_{client_uuid}_wrapped.sql

echo "Recreating database to ensure a clean state..."
mysql -h {conn_info['host']} -P {conn_info['port']} -u {conn_info['user']} -p'{escaped_password}' --connect-timeout=10 -e 'DROP DATABASE IF EXISTS `{conn_info['database']}`; CREATE DATABASE IF NOT EXISTS `{conn_info['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;' mysql 2>&1

echo "Testing database connection..."
if ! timeout 30 mysql -h {conn_info['host']} -P {conn_info['port']} -u {conn_info['user']} -p'{escaped_password}' --connect-timeout=10 -e "SELECT 1;" {conn_info['database']} 2>&1; then
    echo "ERROR: Failed to connect to database"
    rm -f /tmp/create_tables_{client_uuid}.sql /tmp/create_tables_{client_uuid}_wrapped.sql
    exit 1
fi

echo "Executing SQL statements..."
timeout 540 mysql -h {conn_info['host']} -P {conn_info['port']} -u {conn_info['user']} -p'{escaped_password}' --connect-timeout=10 {conn_info['database']} < /tmp/create_tables_{client_uuid}_wrapped.sql 2>&1

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "Tables created successfully"
    rm -f /tmp/create_tables_{client_uuid}.sql /tmp/create_tables_{client_uuid}_wrapped.sql
    exit 0
else
    echo "ERROR: Failed to create tables (exit code: $EXIT_CODE)"
    rm -f /tmp/create_tables_{client_uuid}.sql /tmp/create_tables_{client_uuid}_wrapped.sql
    exit 1
fi
"""

