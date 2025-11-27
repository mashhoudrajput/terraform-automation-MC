/**
 * ============================================================================
 * TERRAFORM OUTPUTS
 * ============================================================================
 * 
 * All outputs from the infrastructure deployment.
 * Use these values to connect services and for documentation.
 * ============================================================================
 */

# ============================================================================
# NETWORKING OUTPUTS
# ============================================================================

output "vpc_id" {
  description = "The ID of the VPC network"
  value       = data.google_compute_network.default.id
}

output "vpc_name" {
  description = "The name of the VPC network"
  value       = data.google_compute_network.default.name
}

output "vpc_self_link" {
  description = "The self link of the VPC network"
  value       = data.google_compute_network.default.self_link
}

output "subnet_id" {
  description = "The ID of the subnet"
  value       = data.google_compute_subnetwork.default.id
}

output "subnet_name" {
  description = "The name of the subnet"
  value       = data.google_compute_subnetwork.default.name
}

output "subnet_cidr" {
  description = "The CIDR range of the subnet"
  value       = data.google_compute_subnetwork.default.ip_cidr_range
}

# ============================================================================
# DATABASE OUTPUTS
# ============================================================================

output "db_instance_name" {
  description = "The name of the Cloud SQL instance"
  value       = local.db_instance_name
}

output "db_instance_connection_name" {
  description = "The connection name for Cloud SQL Proxy"
  value       = google_sql_database_instance.mysql.connection_name
}

output "db_private_ip" {
  description = "The private IP address of the database instance"
  value       = google_sql_database_instance.mysql.private_ip_address
}

output "db_self_link" {
  description = "The self link of the database instance"
  value       = google_sql_database_instance.mysql.self_link
}

output "db_version" {
  description = "The MySQL version running on the instance"
  value       = google_sql_database_instance.mysql.database_version
}

output "database_name" {
  description = "The name of the MySQL database"
  value       = local.database_name
}

output "db_username" {
  description = "The database administrator username"
  value       = google_sql_user.admin.name
}

output "db_password" {
  description = "The auto-generated database password (format: medicalcircle<special><number>)"
  value       = local.db_password
  sensitive   = true
}

output "db_port" {
  description = "The MySQL port number"
  value       = var.db_port
}

# ============================================================================
# DATABASE CONNECTION STRINGS
# ============================================================================

output "mysql_connection_command" {
  description = "MySQL CLI connection command"
  value       = "mysql -h ${google_sql_database_instance.mysql.private_ip_address} -u ${google_sql_user.admin.name} -p -D ${google_sql_database.database.name}"
}

output "jdbc_connection_string" {
  description = "JDBC connection string (password not included)"
  value       = "jdbc:mysql://${google_sql_database_instance.mysql.private_ip_address}:${var.db_port}/${google_sql_database.database.name}?useSSL=false"
}

output "connection_uri" {
  description = "Database connection URI in MySQL format (mysql://username:password@host:port/database)"
  value       = "mysql://${google_sql_user.admin.name}:${local.db_password}@${google_sql_database_instance.mysql.private_ip_address}:${var.db_port}/${local.database_name}"
  sensitive   = true
}

# ============================================================================
# SECRET MANAGER OUTPUTS
# ============================================================================

output "secret_name" {
  description = "The name of the database URI secret in Secret Manager"
  value       = local.secret_name
}

output "secret_id" {
  description = "The full resource ID of the secret"
  value       = google_secret_manager_secret.db_uri.id
}

output "secret_project_number" {
  description = "The project number containing the secret"
  value       = google_secret_manager_secret.db_uri.name
}

output "secret_access_command" {
  description = "gcloud command to retrieve the database URI from Secret Manager"
  value       = "gcloud secrets versions access latest --secret=${google_secret_manager_secret.db_uri.secret_id} --project=${var.project_id}"
}

# ============================================================================
# STORAGE BUCKET OUTPUTS
# ============================================================================

output "private_bucket_name" {
  description = "The name of the private storage bucket"
  value       = google_storage_bucket.private.name
}

output "private_bucket_url" {
  description = "The gs:// URL of the private bucket"
  value       = google_storage_bucket.private.url
}

output "private_bucket_self_link" {
  description = "The self link of the private bucket"
  value       = google_storage_bucket.private.self_link
}

output "public_bucket_name" {
  description = "The name of the public storage bucket"
  value       = google_storage_bucket.public.name
}

output "public_bucket_url" {
  description = "The gs:// URL of the public bucket"
  value       = google_storage_bucket.public.url
}

output "public_bucket_website_url" {
  description = "The HTTPS URL for the public bucket website"
  value       = "https://storage.googleapis.com/${google_storage_bucket.public.name}"
}

output "public_bucket_self_link" {
  description = "The self link of the public bucket"
  value       = google_storage_bucket.public.self_link
}

# ============================================================================
# RESOURCE INFORMATION
# ============================================================================

output "resource_labels" {
  description = "Common labels applied to all resources"
  value       = local.common_labels
}

output "deployment_region" {
  description = "The GCP region where resources are deployed"
  value       = var.region
}

output "environment" {
  description = "The deployment environment"
  value       = var.environment
}

output "cluster_id" {
  description = "The cluster identifier"
  value       = var.cluster_uuid
}

# ============================================================================
# QUICK REFERENCE
# ============================================================================

output "quick_reference" {
  description = "Quick reference guide for common operations"
  value = {
    database = {
      host            = google_sql_database_instance.mysql.private_ip_address
      port            = var.db_port
      database        = google_sql_database.database.name
      username        = google_sql_user.admin.name
      connection_name = google_sql_database_instance.mysql.connection_name
    }
    storage = {
      private_bucket = google_storage_bucket.private.name
      public_bucket  = google_storage_bucket.public.name
    }
    secret_manager = {
      secret_name = google_secret_manager_secret.db_uri.secret_id
      command     = "gcloud secrets versions access latest --secret=${google_secret_manager_secret.db_uri.secret_id}"
    }
    database_init = {
      step1 = "Upload SQL files to a VM in the default VPC"
      step2 = "mysql -h ${google_sql_database_instance.mysql.private_ip_address} -u ${google_sql_user.admin.name} -p -D ${google_sql_database.database.name} < ClusterDB.sql"
      step3 = "mysql -h ${google_sql_database_instance.mysql.private_ip_address} -u ${google_sql_user.admin.name} -p -D ${google_sql_database.database.name} < sn_tables.sql"
    }
  }
}

# ============================================================================
# DATABASE INITIALIZATION SCRIPT
# ============================================================================

output "database_init_script_location" {
  description = "Location of database initialization script in GCS"
  value       = "gs://${google_storage_bucket.private.name}/database-init/${var.cluster_uuid}/init.sh"
}

output "database_init_command" {
  description = "Command to run on existing VM for database initialization"
  value       = "gcloud compute ssh ${var.init_vm_name} --zone=${var.region}-a --command='gsutil cp gs://${google_storage_bucket.private.name}/database-init/${var.cluster_uuid}/init.sh /tmp/ && chmod +x /tmp/init.sh && sudo /tmp/init.sh'"
  sensitive   = false
}