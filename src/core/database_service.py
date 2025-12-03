"""
Database service for executing SQL on hospital databases.
"""
import base64
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple, Optional
from urllib.parse import urlparse
import pymysql
from google.cloud import secretmanager
from google.cloud import storage
from google.oauth2 import service_account

from src.config.settings import settings

logger = logging.getLogger(__name__)


class DatabaseService:
    """Service for executing SQL on hospital databases."""
    
    def __init__(self):
        self._secret_client = None
        self.project_id = settings.gcp_project_id
    
    @property
    def secret_client(self):
        """Lazy initialization of Secret Manager client."""
        if self._secret_client is None:
            try:
                # Try to get credentials from environment or file
                credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
                if not credentials_path:
                    # Try common locations
                    possible_paths = [
                        Path("/app/terraform-sa.json"),
                        Path("/app") / settings.gcp_credentials_file,
                        settings.base_dir / settings.gcp_credentials_file
                    ]
                    for path in possible_paths:
                        if path.exists():
                            credentials_path = str(path)
                            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
                            break
                
                if credentials_path and Path(credentials_path).exists():
                    credentials = service_account.Credentials.from_service_account_file(
                        credentials_path
                    )
                    self._secret_client = secretmanager.SecretManagerServiceClient(
                        credentials=credentials
                    )
                    logger.info(f"Initialized Secret Manager client with credentials from {credentials_path}")
                else:
                    # Fall back to default credentials (for local development)
                    self._secret_client = secretmanager.SecretManagerServiceClient()
                    logger.info("Initialized Secret Manager client with default credentials")
            except Exception as e:
                logger.error(f"Failed to initialize Secret Manager client: {e}")
                raise RuntimeError(f"Failed to initialize Secret Manager client: {e}")
        return self._secret_client
    
    def get_database_connection(self, connection_uri: str) -> pymysql.Connection:
        """
        Create a MySQL connection from connection URI.
        
        Args:
            connection_uri: MySQL connection URI (mysql://user:pass@host:port/database)
            
        Returns:
            MySQL connection object
        """
        # Parse mysql://user:pass@host:port/database
        uri = connection_uri.replace('mysql://', '')
        
        # Extract credentials and connection info
        if '@' in uri:
            auth_part, conn_part = uri.split('@', 1)
            user, password = auth_part.split(':', 1) if ':' in auth_part else (auth_part, '')
        else:
            user, password = '', ''
            conn_part = uri
        
        # Extract host, port, and database
        if '/' in conn_part:
            host_port, database = conn_part.split('/', 1)
        else:
            host_port = conn_part
            database = ''
        
        if ':' in host_port:
            host, port = host_port.split(':', 1)
            port = int(port)
        else:
            host = host_port
            port = 3306
        
        # Remove query parameters if any
        database = database.split('?')[0]
        
        logger.info(f"Connecting to MySQL: {host}:{port}/{database}")
        
        return pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=30
        )
    
    def create_sub_hospital_database(self, parent_uuid: str, sub_hospital_name: str, sub_hospital_uuid: str, private_bucket_name: str = None, region: str = None) -> Tuple[bool, str]:
        """
        Create a new database in the parent hospital's MySQL instance for a sub-hospital.
        Reuses the create_tables method with custom SQL (same VM approach as main hospital).
        
        Args:
            parent_uuid: Parent hospital UUID
            sub_hospital_name: Sub-hospital name (will be used as database name)
            sub_hospital_uuid: Sub-hospital UUID
            private_bucket_name: Parent's private bucket name (for GCS upload)
            region: GCP region (defaults to settings.gcp_region)
            
        Returns:
            Tuple of (success, connection_uri or error_message)
        """
        import re
        
        try:
            region = region or settings.gcp_region
            
            if not private_bucket_name:
                return False, "Private bucket name is required for sub-hospital database creation"
            
            # Get parent's connection URI
            parent_uuid_underscore = parent_uuid.replace('-', '_')
            parent_secret_name = f"{parent_uuid_underscore}_DATABASE_URI"
            parent_connection_uri = self.get_connection_uri_from_secret(parent_secret_name)
            
            # Parse parent connection URI to get connection details
            uri = parent_connection_uri.replace('mysql://', '')
            if '@' in uri:
                auth_part, conn_part = uri.split('@', 1)
                user, password = auth_part.split(':', 1) if ':' in auth_part else (auth_part, '')
            else:
                user, password = '', ''
                conn_part = uri
            
            if '/' in conn_part:
                host_port, _ = conn_part.split('/', 1)
            else:
                host_port = conn_part
            
            if ':' in host_port:
                host, port = host_port.split(':', 1)
                port = int(port)
            else:
                host = host_port
                port = 3306
            
            # Generate database name
            db_name = re.sub(r'[^a-zA-Z0-9_-]', '_', sub_hospital_name.lower())
            db_name = re.sub(r'_+', '_', db_name).strip('_')
            if not db_name:
                db_name = f"sub_{sub_hospital_uuid[:8]}"
            
            logger.info(f"Creating database '{db_name}' for sub-hospital {sub_hospital_uuid} using direct VM command (tested and working)")
            
            # Use direct inline command - tested manually and works perfectly
            # This is simpler and faster than the full script approach
            import subprocess
            import os
            
            vm_zone = settings.db_init_vm_zone or f"{region}-a"
            escaped_password = password.replace("'", "'\"'\"'")
            
            # Direct MySQL command - tested manually and confirmed working
            mysql_command = f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            
            # Use echo to pipe SQL to mysql - simple and reliable (tested manually)
            ssh_command = f"echo '{mysql_command}' | mysql -h {host} -P {port} -u {user} -p'{escaped_password}' mysql 2>&1 && echo 'SUCCESS: Database {db_name} created' || echo 'ERROR: Database creation failed'"
            
            env = os.environ.copy()
            env['GOOGLE_APPLICATION_CREDENTIALS'] = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '/app/terraform-sa.json')
            
            logger.info(f"Executing direct database creation command on VM {settings.db_init_vm_name} in zone {vm_zone}")
            
            try:
                ssh_cmd = [
                    'gcloud', 'compute', 'ssh', settings.db_init_vm_name,
                    '--zone', vm_zone,
                    '--project', settings.gcp_project_id,
                    '--command', ssh_command,
                    '--quiet'
                ]
                
                logger.debug(f"Running: gcloud compute ssh {settings.db_init_vm_name} --zone {vm_zone} --command 'mysql ...'")
                result = subprocess.run(
                    ssh_cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,  # 2 minutes should be enough (manual test took < 5 seconds)
                    env=env
                )
                
                output = (result.stdout or "").strip()
                error_output = (result.stderr or "").strip()
                combined_output = f"{output}\n{error_output}".strip()
                
                logger.info(f"Command completed. Return code: {result.returncode}")
                logger.info(f"Output: {combined_output[:300]}")
                
                if result.returncode == 0 and 'SUCCESS' in output:
                    logger.info(f"Database '{db_name}' created successfully")
                    sub_connection_uri = f"mysql://{user}:{password}@{host}:{port}/{db_name}"
                    logger.info(f"Database '{db_name}' created. Sub-hospital will use parent's secret: {parent_secret_name}")
                    return True, sub_connection_uri
                else:
                    error_msg = combined_output or "Unknown error"
                    logger.error(f"Database creation failed. Return code: {result.returncode}")
                    logger.error(f"Full output: {error_msg[:500]}")
                    return False, f"Failed to create database: {error_msg[:200]}"
                    
            except subprocess.TimeoutExpired as e:
                error_msg = "Database creation timed out after 2 minutes. Please check VM and database connectivity."
                logger.error(error_msg)
                return False, error_msg
            except Exception as e:
                error_msg = f"Failed to create database: {str(e)}"
                logger.error(error_msg, exc_info=True)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Failed to create sub-hospital database: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def get_connection_uri_from_secret(self, secret_name: str) -> str:
        """
        Get database connection URI from Secret Manager.
        
        Args:
            secret_name: Name of the secret in Secret Manager
            
        Returns:
            Connection URI string
        """
        try:
            secret_path = f"projects/{self.project_id}/secrets/{secret_name}/versions/latest"
            response = self.secret_client.access_secret_version(request={"name": secret_path})
            connection_uri = response.payload.data.decode("UTF-8")
            logger.info(f"Retrieved connection URI from secret: {secret_name}")
            return connection_uri
        except Exception as e:
            logger.error(f"Failed to retrieve secret {secret_name}: {str(e)}")
            raise
    
    def execute_sql_file(self, connection_uri: str, sql_file_path: Path) -> Tuple[bool, str]:
        """
        Execute SQL file on the database.
        
        Args:
            connection_uri: MySQL connection URI
            sql_file_path: Path to SQL file
            
        Returns:
            Tuple of (success, message)
        """
        if not sql_file_path.exists():
            return False, f"SQL file not found: {sql_file_path}"
        
        try:
            # Read SQL file
            sql_content = sql_file_path.read_text(encoding='utf-8')
            
            # Remove multi-line comments /* ... */
            sql_content = re.sub(r'/\*.*?\*/', '', sql_content, flags=re.DOTALL)
            
            # Split by semicolon and filter out empty statements
            statements = []
            current_statement = []
            
            for line in sql_content.split('\n'):
                # Remove single-line comments
                line = re.sub(r'--.*$', '', line)
                line = line.strip()
                
                if not line:
                    continue
                
                current_statement.append(line)
                
                # Check if line ends with semicolon
                if line.endswith(';'):
                    statement = ' '.join(current_statement)
                    if statement.strip() and statement.strip() != ';':
                        statements.append(statement)
                    current_statement = []
            
            # Add any remaining statement
            if current_statement:
                statement = ' '.join(current_statement)
                if statement.strip():
                    statements.append(statement)
            
            logger.info(f"Executing {len(statements)} SQL statements from {sql_file_path}")
            
            # Connect to database
            connection = self.get_database_connection(connection_uri)
            
            try:
                with connection.cursor() as cursor:
                    for i, statement in enumerate(statements, 1):
                        if statement.strip():
                            try:
                                cursor.execute(statement)
                                logger.debug(f"Executed statement {i}/{len(statements)}")
                            except Exception as e:
                                logger.error(f"Error executing statement {i}: {str(e)}")
                                connection.rollback()
                                return False, f"Error executing statement {i}: {str(e)}"
                    
                    connection.commit()
                    logger.info(f"Successfully executed {len(statements)} SQL statements")
                    return True, f"Successfully executed {len(statements)} SQL statements"
                    
            finally:
                connection.close()
                
        except Exception as e:
            error_msg = f"Failed to execute SQL file: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def upload_sql_to_bucket(self, bucket_name: str, client_uuid: str, sql_content: str, sql_filename: str = "ClusterDB.sql") -> Tuple[bool, str]:
        """
        Upload SQL file to GCS bucket.
        
        Args:
            bucket_name: GCS bucket name
            client_uuid: Client UUID
            sql_content: SQL file content
            sql_filename: SQL filename (default: ClusterDB.sql)
            
        Returns:
            Tuple of (success, gcs_path)
        """
        try:
            storage_client = storage.Client(project=settings.gcp_project_id)
            bucket = storage_client.bucket(bucket_name)
            
            blob_path = f"database-init/{client_uuid}/{sql_filename}"
            blob = bucket.blob(blob_path)
            
            blob.upload_from_string(sql_content, content_type='text/plain')
            gcs_path = f"gs://{bucket_name}/{blob_path}"
            
            logger.info(f"Uploaded SQL file to {gcs_path}")
            return True, gcs_path
            
        except Exception as e:
            error_msg = f"Failed to upload SQL to bucket: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def create_tables(self, client_uuid: str, is_sub_hospital: bool = False, region: str = None, private_bucket_name: str = None, parent_uuid: str = None, database_name: str = None, custom_sql_content: str = None, custom_sql_filename: str = None) -> Tuple[bool, str]:
        """
        Create tables in the hospital database using ClusterDB.sql or sn_tables.sql.
        Executes SQL from a VM within the VPC since database has private IP only.
        
        Args:
            client_uuid: Client UUID
            is_sub_hospital: Whether this is a sub-hospital
            region: GCP region (defaults to settings.gcp_region)
            private_bucket_name: Private bucket name (from terraform outputs)
            parent_uuid: Parent hospital UUID (required for sub-hospitals)
            database_name: Database name (for sub-hospitals)
            custom_sql_content: Optional custom SQL content (if provided, uses this instead of reading from file)
            custom_sql_filename: Optional custom SQL filename (used with custom_sql_content)
            
        Returns:
            Tuple of (success, message)
        """
        try:
            region = region or settings.gcp_region
            vm_zone = settings.db_init_vm_zone or f"{region}-a"
            
            if not private_bucket_name:
                return False, "Private bucket name is required"
            
            # For sub-hospitals, use parent's secret; for main hospitals, use own secret
            if is_sub_hospital:
                if not parent_uuid:
                    return False, "Parent UUID is required for sub-hospital table creation"
                # Use parent's secret and connection string
                parent_uuid_underscore = parent_uuid.replace('-', '_')
                secret_name = f"{parent_uuid_underscore}_DATABASE_URI"
                logger.info(f"Sub-hospital {client_uuid} using parent's secret: {secret_name}")
            else:
                # Use own secret
                cluster_uuid_underscore = client_uuid.replace('-', '_')
                secret_name = f"{cluster_uuid_underscore}_DATABASE_URI"
            
            connection_uri = self.get_connection_uri_from_secret(secret_name)
            
            # Parse connection URI to get connection details
            uri = connection_uri.replace('mysql://', '')
            if '@' in uri:
                auth_part, conn_part = uri.split('@', 1)
                user, password = auth_part.split(':', 1) if ':' in auth_part else (auth_part, '')
            else:
                user, password = '', ''
                conn_part = uri
            
            if '/' in conn_part:
                host_port, database = conn_part.split('/', 1)
            else:
                host_port = conn_part
                database = ''
            
            if ':' in host_port:
                host, port = host_port.split(':', 1)
            else:
                host = host_port
                port = 3306
            
            database = database.split('?')[0]
            
            if is_sub_hospital and database_name:
                database = database_name
                logger.info(f"Using sub-hospital database name: {database}")
            
            # Use custom SQL content if provided, otherwise read from file
            if custom_sql_content and custom_sql_filename:
                sql_content = custom_sql_content
                sql_filename = custom_sql_filename
                logger.info(f"Using custom SQL content for {sql_filename}")
            else:
                sql_filename = "sn_tables.sql" if is_sub_hospital else "ClusterDB.sql"
                sql_file_path = None
                possible_paths = [
                    Path(f"/app/infrastructure/base/sql/{sql_filename}"),
                    settings.base_dir / "infrastructure" / "base" / "sql" / sql_filename,
                    Path(f"/app/infrastructure/base/sql/{sql_filename}")
                ]
                
                for path in possible_paths:
                    if path.exists():
                        sql_file_path = path
                        break
                
                if not sql_file_path or not sql_file_path.exists():
                    return False, f"{sql_filename} file not found. Searched: {[str(p) for p in possible_paths]}"
                
                sql_content = sql_file_path.read_text(encoding='utf-8')
            logger.info(f"Uploading {sql_filename} file to bucket {private_bucket_name}...")
            upload_success, gcs_path = self.upload_sql_to_bucket(private_bucket_name, client_uuid, sql_content, sql_filename)
            if not upload_success:
                return False, f"Failed to upload SQL file: {gcs_path}"
            
            escaped_password = password.replace("'", "'\"'\"'")
            
            gcs_sql_path = f"gs://{private_bucket_name}/database-init/{client_uuid}/{sql_filename}"
            
            # Determine if we're creating a database (custom SQL with CREATE DATABASE)
            is_creating_database = custom_sql_content and 'CREATE DATABASE' in custom_sql_content.upper()
            # For database creation, connect to mysql system database; otherwise use target database
            connection_database = 'mysql' if is_creating_database else database
            
            script_content = f"""#!/bin/bash
set -e

echo "Starting table creation process"
echo "Timestamp: $(date)"
echo ""

echo "Step 1: Testing VM connectivity..."
PUBLIC_IP=$(curl -s ifconfig.io 2>/dev/null || echo "N/A")
echo "VM Public IP: $PUBLIC_IP"
echo ""

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
echo ""

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
echo ""

echo "Step 4: Downloading SQL file from GCS..."
echo "Source: {gcs_sql_path}"
if gsutil cp {gcs_sql_path} /tmp/create_tables_{client_uuid}.sql; then
    echo "SQL file downloaded successfully"
    echo "File size: $(wc -l < /tmp/create_tables_{client_uuid}.sql) lines"
else
    echo "ERROR: Failed to download SQL file from GCS"
    exit 1
fi
echo ""

echo "Step 5: Testing database connection..."
echo "Connecting to {host}:{port}/{connection_database}..."
if timeout 30 mysql -h {host} -P {port} -u {user} -p'{escaped_password}' --connect-timeout=10 -e "SELECT 1 as connection_test;" {connection_database} 2>&1; then
    echo "Database connection successful"
else
    echo "ERROR: Failed to connect to database"
    echo "Please check database is running and credentials are correct"
    rm -f /tmp/create_tables_{client_uuid}.sql
    exit 1
fi
echo ""

echo "Step 6: Executing SQL statements..."
echo "Starting at: $(date)"
timeout 540 mysql -h {host} -P {port} -u {user} -p'{escaped_password}' --connect-timeout=10 {connection_database} < /tmp/create_tables_{client_uuid}.sql 2>&1

EXIT_CODE=$?
echo ""
echo "Completed at: $(date)"

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
            
            logger.info(f"Executing SQL on VM {settings.db_init_vm_name} in zone {vm_zone}")
            
            env = os.environ.copy()
            env['GOOGLE_APPLICATION_CREDENTIALS'] = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '/app/terraform-sa.json')
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as tmp_script:
                tmp_script.write(script_content)
                tmp_script_path = tmp_script.name
                os.chmod(tmp_script_path, 0o755)
            
            try:
                # Verify gcloud is available
                try:
                    gcloud_check = subprocess.run(
                        ['gcloud', '--version'],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if gcloud_check.returncode != 0:
                        return False, "gcloud CLI is not properly installed"
                    logger.info(f"gcloud version: {gcloud_check.stdout.split()[0] if gcloud_check.stdout else 'unknown'}")
                except FileNotFoundError:
                    return False, "gcloud CLI not found. Please ensure Google Cloud SDK is installed."
                
                # Test SSH connectivity first
                logger.info(f"Testing SSH connectivity to VM {settings.db_init_vm_name}...")
                test_cmd = [
                    'gcloud', 'compute', 'ssh', settings.db_init_vm_name,
                    '--zone', vm_zone,
                    '--project', settings.gcp_project_id,
                    '--command', 'echo "SSH connection successful" && curl -s ifconfig.io'
                ]
                
                test_result = subprocess.run(
                    test_cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=env
                )
                
                if test_result.returncode == 0:
                    logger.info(f"SSH connectivity test passed. VM IP: {test_result.stdout.strip()}")
                else:
                    error_detail = test_result.stderr or test_result.stdout
                    logger.warning(f"SSH connectivity test had issues: {error_detail[:200]}")
                    # Continue anyway, might still work
                
                # Copy script to VM
                logger.info(f"Copying script to VM {settings.db_init_vm_name} in zone {vm_zone}...")
                scp_cmd = [
                    'gcloud', 'compute', 'scp',
                    tmp_script_path,
                    f'{settings.db_init_vm_name}:/tmp/create_tables_{client_uuid}.sh',
                    '--zone', vm_zone,
                    '--project', settings.gcp_project_id,
                    '--quiet'
                ]
                
                logger.debug(f"Running: {' '.join(scp_cmd)}")
                scp_result = subprocess.run(
                    scp_cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=env
                )
                
                if scp_result.returncode != 0:
                    error_detail = scp_result.stderr or scp_result.stdout
                    logger.error(f"SCP failed: {error_detail}")
                    return False, f"Failed to copy script to VM: {error_detail}"
                
                logger.info("Script copied successfully")
                
                # Execute script on VM
                logger.info(f"Executing script on VM {settings.db_init_vm_name}...")
                ssh_cmd = [
                    'gcloud', 'compute', 'ssh', settings.db_init_vm_name,
                    '--zone', vm_zone,
                    '--project', settings.gcp_project_id,
                    '--command', f'sudo bash /tmp/create_tables_{client_uuid}.sh'
                ]
                
                logger.debug(f"Running: {' '.join(ssh_cmd[:6])}...")
                result = subprocess.run(
                    ssh_cmd,
                    capture_output=True,
                    text=True,
                    timeout=600,  # 10 minutes timeout (SQL execution can take time)
                    env=env
                )
                
                if result.returncode == 0:
                    logger.info("Tables created successfully")
                    if result.stdout:
                        logger.info(f"Script output: {result.stdout[:500]}")  # Log first 500 chars
                    return True, "Tables created successfully"
                else:
                    # Capture both stdout and stderr for better debugging
                    output = result.stdout or ""
                    error_output = result.stderr or ""
                    combined_output = f"{output}\n{error_output}".strip()
                    
                    # Log full output for debugging
                    logger.error(f"Script execution failed. Return code: {result.returncode}")
                    logger.error(f"Stdout: {output[:1000] if output else 'None'}")
                    logger.error(f"Stderr: {error_output[:1000] if error_output else 'None'}")
                    
                    error_msg = f"Failed to create tables: {combined_output[:500] if combined_output else 'Unknown error'}"
                    return False, error_msg
                    
            finally:
                # Clean up temp file
                try:
                    os.unlink(tmp_script_path)
                except:
                    pass
            
        except subprocess.TimeoutExpired:
            error_msg = "Table creation timed out after 10 minutes. The SQL execution may be taking longer than expected. Please check the VM and database connectivity."
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Failed to create tables: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

