/**
 * ============================================================================
 * TERRAFORM VARIABLES
 * ============================================================================
 * 
 * All configurable parameters for the infrastructure.
 * Override these in terraform.tfvars or via command line.
 * ============================================================================
 */

# ============================================================================
# PROJECT CONFIGURATION
# ============================================================================

variable "project_id" {
  description = "The GCP project ID where resources will be created"
  type        = string
  default     = "lively-synapse-400818"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Project ID must be a valid GCP project identifier."
  }
}

variable "region" {
  description = "The GCP region for deploying resources"
  type        = string
  default     = "me-central2"

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]$", var.region))
    error_message = "Region must be a valid GCP region (e.g., us-central1, me-central2)."
  }
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "cluster_uuid" {
  description = "Unique identifier for this cluster/deployment"
  type        = string
  default     = "cluster-001"

  validation {
    condition     = length(var.cluster_uuid) >= 3 && length(var.cluster_uuid) <= 63
    error_message = "Cluster UUID must be between 3 and 63 characters."
  }
}

variable "is_sub_hospital" {
  description = "Whether this is a sub-hospital (uses parent's infrastructure)"
  type        = bool
  default     = false
}

variable "parent_instance_name" {
  description = "Parent Cloud SQL instance name (required for sub-hospitals)"
  type        = string
  default     = ""
}

variable "hospital_name" {
  description = "Hospital name (used for database name, sanitized)"
  type        = string
  default     = ""
}

variable "created_date" {
  description = "Creation date for resource labels (YYYY-MM-DD format)"
  type        = string
  default     = "2025-11-24"

  validation {
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", var.created_date))
    error_message = "Created date must be in YYYY-MM-DD format."
  }
}

# ============================================================================
# NETWORKING CONFIGURATION
# ============================================================================

variable "vpc_name" {
  description = "Name of the VPC network to use"
  type        = string
  default     = "default"
}

variable "subnet_name" {
  description = "Name of the subnet to use"
  type        = string
  default     = "default"
}

variable "private_ip_allocation_name" {
  description = "Name of the private IP address allocation for Cloud SQL"
  type        = string
  default     = "private-ip"
}

variable "allowed_ip_ranges" {
  description = "List of IP ranges allowed to access the MySQL instance"
  type        = list(string)
  default     = ["10.0.0.0/8"]

  validation {
    condition     = alltrue([for cidr in var.allowed_ip_ranges : can(cidrhost(cidr, 0))])
    error_message = "All entries must be valid CIDR blocks."
  }
}

variable "db_port" {
  description = "MySQL port number"
  type        = string
  default     = "3306"
}

# ============================================================================
# CLOUD SQL CONFIGURATION
# ============================================================================

variable "db_instance_name" {
  description = "Name of the Cloud SQL instance (empty = auto-generate: mc-cluster-<cluster_uuid>)"
  type        = string
  default     = ""

  validation {
    condition     = var.db_instance_name == "" || can(regex("^[a-z][a-z0-9-]{0,61}[a-z0-9]$", var.db_instance_name))
    error_message = "Instance name must start with a letter, contain only lowercase letters, numbers, and hyphens."
  }
}

variable "database_version" {
  description = "MySQL database version"
  type        = string
  default     = "MYSQL_8_0"

  validation {
    condition     = contains(["MYSQL_5_7", "MYSQL_8_0"], var.database_version)
    error_message = "Database version must be MYSQL_5_7 or MYSQL_8_0."
  }
}

variable "db_tier" {
  description = "Machine type for the database instance"
  type        = string
  default     = "db-f1-micro"
}

variable "availability_type" {
  description = "Availability type (ZONAL for single zone, REGIONAL for high availability)"
  type        = string
  default     = "ZONAL"

  validation {
    condition     = contains(["ZONAL", "REGIONAL"], var.availability_type)
    error_message = "Availability type must be ZONAL or REGIONAL."
  }
}

variable "disk_size" {
  description = "Disk size in GB for the database instance"
  type        = number
  default     = 10

  validation {
    condition     = var.disk_size >= 10 && var.disk_size <= 65536
    error_message = "Disk size must be between 10 GB and 65536 GB."
  }
}

variable "disk_type" {
  description = "Type of disk (PD_SSD for SSD, PD_HDD for HDD)"
  type        = string
  default     = "PD_SSD"

  validation {
    condition     = contains(["PD_SSD", "PD_HDD"], var.disk_type)
    error_message = "Disk type must be PD_SSD or PD_HDD."
  }
}

variable "disk_autoresize" {
  description = "Enable automatic storage increase"
  type        = bool
  default     = true
}

variable "deletion_protection" {
  description = "Enable deletion protection for the database instance"
  type        = bool
  default     = false
}

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

variable "database_name" {
  description = "Name of the MySQL database to create (empty = auto-generate: cluster_<cluster_uuid>)"
  type        = string
  default     = ""

  validation {
    condition     = var.database_name == "" || can(regex("^[a-zA-Z][a-zA-Z0-9_]{0,63}$", var.database_name))
    error_message = "Database name must start with a letter and contain only alphanumeric characters and underscores."
  }
}

variable "db_user" {
  description = "MySQL database administrator username"
  type        = string
  default     = "root"

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9_]{2,31}$", var.db_user))
    error_message = "Database user must start with a letter and be 3-32 characters long."
  }
}

variable "db_password_length" {
  description = "(DEPRECATED) Password now generated as random 8-character base64 string."
  type        = number
  default     = 16

  validation {
    condition     = var.db_password_length >= 12 && var.db_password_length <= 128
    error_message = "Password length must be between 12 and 128 characters."
  }
}

variable "max_connections" {
  description = "Maximum number of database connections"
  type        = string
  default     = "1000"
}

# ============================================================================
# BACKUP CONFIGURATION
# ============================================================================

variable "backup_enabled" {
  description = "Enable automated backups"
  type        = bool
  default     = true
}

variable "binary_log_enabled" {
  description = "Enable binary logging for point-in-time recovery"
  type        = bool
  default     = true
}

variable "backup_start_time" {
  description = "Start time for automated backups (HH:MM format in UTC)"
  type        = string
  default     = "03:00"

  validation {
    condition     = can(regex("^([0-1][0-9]|2[0-3]):[0-5][0-9]$", var.backup_start_time))
    error_message = "Backup start time must be in HH:MM format (24-hour)."
  }
}

variable "transaction_log_retention_days" {
  description = "Number of days to retain transaction logs"
  type        = number
  default     = 7

  validation {
    condition     = var.transaction_log_retention_days >= 1 && var.transaction_log_retention_days <= 7
    error_message = "Transaction log retention must be between 1 and 7 days."
  }
}

variable "backup_retained_count" {
  description = "Number of automated backups to retain"
  type        = number
  default     = 7

  validation {
    condition     = var.backup_retained_count >= 1 && var.backup_retained_count <= 365
    error_message = "Backup retention must be between 1 and 365 backups."
  }
}

# ============================================================================
# MAINTENANCE WINDOW
# ============================================================================

variable "maintenance_window_day" {
  description = "Day of week for maintenance (1-7, where 1 is Monday)"
  type        = number
  default     = 7

  validation {
    condition     = var.maintenance_window_day >= 1 && var.maintenance_window_day <= 7
    error_message = "Maintenance day must be between 1 (Monday) and 7 (Sunday)."
  }
}

variable "maintenance_window_hour" {
  description = "Hour of day for maintenance (0-23, UTC)"
  type        = number
  default     = 2

  validation {
    condition     = var.maintenance_window_hour >= 0 && var.maintenance_window_hour <= 23
    error_message = "Maintenance hour must be between 0 and 23."
  }
}

variable "maintenance_window_update_track" {
  description = "Maintenance timing (stable or canary)"
  type        = string
  default     = "stable"

  validation {
    condition     = contains(["stable", "canary"], var.maintenance_window_update_track)
    error_message = "Update track must be 'stable' or 'canary'."
  }
}

# ============================================================================
# SECRET MANAGER CONFIGURATION
# ============================================================================

variable "secret_name" {
  description = "Name of the secret in Secret Manager (empty = auto-generate: <cluster_uuid>_DATABASE_URI)"
  type        = string
  default     = ""

  validation {
    condition     = var.secret_name == "" || can(regex("^[a-zA-Z0-9][a-zA-Z0-9_-]{0,254}$", var.secret_name))
    error_message = "Secret name must start with a letter or number and contain only letters, numbers, hyphens, and underscores (1-255 characters)."
  }
}

# ============================================================================
# STORAGE BUCKET CONFIGURATION
# ============================================================================

variable "storage_class" {
  description = "Storage class for GCS buckets"
  type        = string
  default     = "STANDARD"

  validation {
    condition     = contains(["STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"], var.storage_class)
    error_message = "Storage class must be STANDARD, NEARLINE, COLDLINE, or ARCHIVE."
  }
}

variable "bucket_force_destroy" {
  description = "Allow deletion of non-empty buckets"
  type        = bool
  default     = true
}

variable "enable_versioning" {
  description = "Enable object versioning on private bucket"
  type        = bool
  default     = true
}

variable "lifecycle_age_days" {
  description = "Days after which to delete old object versions"
  type        = number
  default     = 365

  validation {
    condition     = var.lifecycle_age_days >= 1
    error_message = "Lifecycle age must be at least 1 day."
  }
}

variable "bucket_encryption_key" {
  description = "KMS key for bucket encryption (optional)"
  type        = string
  default     = null
}

variable "enable_public_bucket" {
  description = "Enable public access to the public bucket"
  type        = bool
  default     = true
}

# ============================================================================
# WEBSITE CONFIGURATION
# ============================================================================

variable "website_main_page" {
  description = "Main page for bucket website"
  type        = string
  default     = "index.html"
}

variable "website_error_page" {
  description = "Error page for bucket website"
  type        = string
  default     = "404.html"
}

# ============================================================================
# CORS CONFIGURATION
# ============================================================================

variable "cors_origins" {
  description = "List of origins allowed for CORS"
  type        = list(string)
  default     = ["*"]
}

variable "cors_methods" {
  description = "List of HTTP methods allowed for CORS"
  type        = list(string)
  default     = ["GET", "HEAD"]
}

variable "cors_response_headers" {
  description = "List of response headers allowed for CORS"
  type        = list(string)
  default     = ["*"]
}

variable "cors_max_age_seconds" {
  description = "Max age in seconds for CORS preflight cache"
  type        = number
  default     = 3600

  validation {
    condition     = var.cors_max_age_seconds >= 0
    error_message = "CORS max age must be non-negative."
  }
}
