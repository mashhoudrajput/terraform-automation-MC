#!/bin/bash
set -euo pipefail

# Database connection parameters (Terraform will replace these)
DB_HOST="${db_host}"
DB_USER="${db_user}"
DB_PASSWORD="${db_password}"
DB_NAME="${db_name}"
BUCKET_NAME="${bucket_name}"
CLUSTER_UUID="${cluster_uuid}"
IS_SUB_HOSPITAL="${is_sub_hospital}"
PROJECT_ID="${project_id}"
PARENT_UUID="${parent_uuid}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "$${GREEN}[INFO]$${NC} $${1}"
}

log_warn() {
    echo -e "$${YELLOW}[WARN]$${NC} $${1}"
}

log_error() {
    echo -e "$${RED}[ERROR]$${NC} $${1}"
}

# Function to get parent database credentials from Secret Manager
get_parent_credentials() {
    local parent_secret_name="$${PARENT_UUID}_DATABASE_URI"
    log_info "Retrieving parent database credentials from Secret Manager: $${parent_secret_name}"
    
    local db_uri
    db_uri=$$(gcloud secrets versions access latest --secret="$${parent_secret_name}" --project="$${PROJECT_ID}" 2>/dev/null || echo "")
    
    if [ -z "$${db_uri}" ]; then
        log_error "Failed to retrieve parent database URI from Secret Manager"
        exit 1
    fi
    
    # Extract credentials from mysql://user:password@host:port/database
    # Remove mysql:// prefix
    local uri_part
    uri_part=$${db_uri#mysql://}
    # Extract user (before :)
    DB_USER=$$(echo "$${uri_part}" | sed -n 's/\([^:]*\):.*/\1/p')
    # Extract password (between : and @)
    DB_PASSWORD=$$(echo "$${uri_part}" | sed -n 's/.*:\([^@]*\)@.*/\1/p')
    
    if [ -z "$${DB_USER}" ] || [ -z "$${DB_PASSWORD}" ]; then
        log_error "Failed to extract user or password from database URI"
        exit 1
    fi
    
    log_info "Successfully retrieved parent database credentials (user: $${DB_USER})"
}

# Install MySQL client if not present
install_mysql_client() {
    if ! command -v mysql &> /dev/null; then
        log_info "Installing MySQL client..."
        if command -v apt-get &> /dev/null; then
            sudo apt-get update -qq
            sudo apt-get install -y -qq mysql-client
        elif command -v yum &> /dev/null; then
            sudo yum install -y -q mysql
        else
            log_error "Cannot install MySQL client: package manager not found"
            exit 1
        fi
    fi
}

# Wait for database to be ready
wait_for_database() {
    log_info "Waiting for database to be ready..."
    local max_attempts=30
    local attempt=1
    
    while [ $${attempt} -le $${max_attempts} ]; do
        if mysql -h "$${DB_HOST}" -u "$${DB_USER}" -p"$${DB_PASSWORD}" -e "SELECT 1;" &>/dev/null; then
            log_info "Database is ready"
            return 0
        fi
        log_info "Attempt $${attempt}/$${max_attempts}: Database not ready yet, waiting 10 seconds..."
        sleep 10
        attempt=$$((attempt + 1))
    done
    
    log_error "Database did not become ready after $${max_attempts} attempts"
    return 1
}

# Download SQL files from GCS
download_sql_files() {
    local temp_dir="/tmp/db-init-$${CLUSTER_UUID}"
    mkdir -p "$${temp_dir}"
    
    log_info "Downloading SQL files from GCS bucket: $${BUCKET_NAME}"
    
    if [ "$${IS_SUB_HOSPITAL}" = "true" ]; then
        # Sub-Hospital: Download only sn_tables.sql
        if gsutil cp "gs://$${BUCKET_NAME}/database-init/$${CLUSTER_UUID}/sn_tables.sql" "$${temp_dir}/sn_tables.sql" 2>/dev/null; then
            log_info "Downloaded sn_tables.sql"
        else
            log_error "Failed to download sn_tables.sql"
            exit 1
        fi
    else
        # Main Hospital: Download only ClusterDB.sql
        if gsutil cp "gs://$${BUCKET_NAME}/database-init/$${CLUSTER_UUID}/ClusterDB.sql" "$${temp_dir}/ClusterDB.sql" 2>/dev/null; then
            log_info "Downloaded ClusterDB.sql"
        else
            log_error "Failed to download ClusterDB.sql"
            exit 1
        fi
    fi
    
    echo "$${temp_dir}"
}

# Execute SQL file
execute_sql_file() {
    local sql_file="$${1}"
    local description="$${2}"
    
    log_info "Executing $${description}..."
    
    if mysql -h "$${DB_HOST}" -u "$${DB_USER}" -p"$${DB_PASSWORD}" "$${DB_NAME}" < "$${sql_file}"; then
        log_info "Successfully executed $${description}"
        return 0
    else
        log_error "Failed to execute $${description}"
        return 1
    fi
}

# Main execution
main() {
    log_info "Starting database initialization for cluster: $${CLUSTER_UUID}"
    log_info "Database: $${DB_NAME} on $${DB_HOST}"
    log_info "Is Sub-Hospital: $${IS_SUB_HOSPITAL}"
    
    # Get parent credentials for sub-hospitals
    if [ "$${IS_SUB_HOSPITAL}" = "true" ]; then
        if [ -z "$${DB_PASSWORD}" ]; then
            get_parent_credentials
        fi
    fi
    
    # Install MySQL client
    install_mysql_client
    
    # Wait for database to be ready
    if ! wait_for_database; then
        exit 1
    fi
    
    # Download SQL files
    local temp_dir
    temp_dir=$$(download_sql_files)
    
    # Execute SQL files based on hospital type
    if [ "$${IS_SUB_HOSPITAL}" = "true" ]; then
        # Sub-Hospital: Only run sn_tables.sql
        log_info "Sub-Hospital detected: Running sn_tables.sql only"
        if ! execute_sql_file "$${temp_dir}/sn_tables.sql" "sn_tables.sql (Sub-Hospital tables)"; then
            exit 1
        fi
    else
        # Main Hospital: Run only ClusterDB.sql
        log_info "Main Hospital detected: Running ClusterDB.sql only"
        if ! execute_sql_file "$${temp_dir}/ClusterDB.sql" "ClusterDB.sql (Main-Hospital tables)"; then
            exit 1
        fi
    fi
    
    # Cleanup
    log_info "Cleaning up temporary files..."
    rm -rf "$${temp_dir}"
    
    log_info "Database initialization completed successfully!"
}

# Run main function
main "$$@"
