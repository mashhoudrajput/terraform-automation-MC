locals {
  resource_prefix = "${var.environment}-${var.region}"

  common_labels = {
    environment  = var.environment
    managed_by   = "terraform"
    project      = var.project_id
    cluster_id   = var.cluster_uuid
    created_date = var.created_date
  }

  db_flags = {
    character_set_server = "utf8mb4"
    max_connections      = var.max_connections
    slow_query_log       = "on"
    log_output           = "FILE"
  }

  cluster_uuid_underscore = replace(var.cluster_uuid, "-", "_")
  parent_uuid_underscore = var.is_sub_hospital ? replace(replace(var.parent_instance_name, "mc-cluster-", ""), "-", "_") : ""
  
  sanitized_hospital_name = lower(replace(replace(replace(replace(var.hospital_name, " ", "_"), "-", "_"), ".", "_"), "/", "_"))
  
  db_instance_name = var.is_sub_hospital ? var.parent_instance_name : (var.db_instance_name != "" ? var.db_instance_name : "mc-cluster-${var.cluster_uuid}")
  database_name    = var.database_name != "" ? var.database_name : (var.hospital_name != "" ? local.sanitized_hospital_name : "cluster_${local.cluster_uuid_underscore}")
  secret_name      = var.secret_name != "" ? var.secret_name : "${local.cluster_uuid_underscore}_DATABASE_URI"
  
  private_bucket_name = "${local.cluster_uuid_underscore}_private_${var.environment}"
  public_bucket_name  = "${local.cluster_uuid_underscore}_public_${var.environment}"
}

resource "random_id" "db_password" {
  byte_length = 8

  lifecycle {
    ignore_changes = all
  }
}

locals {
  db_password = random_id.db_password.b64_std
}

data "google_compute_network" "default" {
  name = var.vpc_name
}

data "google_compute_subnetwork" "default" {
  name   = var.subnet_name
  region = var.region
}

data "google_compute_global_address" "private_ip_address" {
  name = var.private_ip_allocation_name
}

resource "google_service_networking_connection" "private_vpc_connection" {
  count                  = var.is_sub_hospital ? 0 : 1
  network                 = data.google_compute_network.default.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [data.google_compute_global_address.private_ip_address.name]
  deletion_policy         = "ABANDON"
}

resource "google_compute_firewall" "mysql_internal" {
  count       = var.is_sub_hospital ? 0 : 1
  name        = "fw-mysql-${var.environment != "" ? var.environment : "env"}-${replace(var.cluster_uuid, "_", "-")}"
  network     = data.google_compute_network.default.self_link
  description = "Allow MySQL (${var.db_port}) access from internal VPC - ${var.environment}"
  priority    = 1000

  allow {
    protocol = "tcp"
    ports    = [var.db_port]
  }

  source_ranges = var.allowed_ip_ranges
  target_tags   = ["mysql-client"]
}

resource "google_sql_database_instance" "mysql" {
  count               = var.is_sub_hospital ? 0 : 1
  name                = local.db_instance_name
  database_version    = var.database_version
  region              = var.region
  deletion_protection = var.deletion_protection

  depends_on = [google_service_networking_connection.private_vpc_connection[0]]

  settings {
    tier              = var.db_tier
    availability_type = var.availability_type
    disk_size         = var.disk_size
    disk_type         = var.disk_type
    disk_autoresize   = var.disk_autoresize

    user_labels = merge(
      local.common_labels,
      {
        component = "database"
        db_type   = "mysql"
      }
    )

    backup_configuration {
      enabled                        = var.backup_enabled
      binary_log_enabled             = var.binary_log_enabled
      start_time                     = var.backup_start_time
      transaction_log_retention_days = var.transaction_log_retention_days

      backup_retention_settings {
        retained_backups = var.backup_retained_count
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = data.google_compute_network.default.id
      enable_private_path_for_google_cloud_services = true
    }

    dynamic "database_flags" {
      for_each = local.db_flags
      content {
        name  = database_flags.key
        value = database_flags.value
      }
    }

    maintenance_window {
      day          = var.maintenance_window_day
      hour         = var.maintenance_window_hour
      update_track = var.maintenance_window_update_track
    }

    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = true
      record_client_address   = true
    }
  }

  lifecycle {
    prevent_destroy = false
    ignore_changes  = [settings[0].disk_size]
  }
}

resource "google_sql_database" "database" {
  name      = local.database_name
  instance  = var.is_sub_hospital ? var.parent_instance_name : google_sql_database_instance.mysql[0].name
  charset   = "utf8mb4"
  collation = "utf8mb4_unicode_ci"
}

resource "google_sql_user" "admin" {
  count    = var.is_sub_hospital ? 0 : 1
  name     = var.db_user
  instance = google_sql_database_instance.mysql[0].name
  host     = "%"
  password = local.db_password
}

data "google_sql_database_instance" "parent" {
  count   = var.is_sub_hospital ? 1 : 0
  name    = var.parent_instance_name
  project = var.project_id
}


data "google_secret_manager_secret_version" "parent_db_uri" {
  count   = var.is_sub_hospital ? 1 : 0
  secret  = "${replace(replace(var.parent_instance_name, "mc-cluster-", ""), "-", "_")}_DATABASE_URI"
  project = var.project_id
}

resource "google_secret_manager_secret" "db_uri" {
  secret_id = local.secret_name
  project   = var.project_id

  replication {
    auto {}
  }

  labels = merge(
    local.common_labels,
    {
      component = "database"
      type      = "connection-uri"
    }
  )

  lifecycle {
    prevent_destroy = false
  }
}

resource "google_secret_manager_secret_version" "db_uri" {
  secret    = google_secret_manager_secret.db_uri.id
  secret_data = var.is_sub_hospital ? replace(
    data.google_secret_manager_secret_version.parent_db_uri[0].secret_data,
    regex("/[^/]+$", data.google_secret_manager_secret_version.parent_db_uri[0].secret_data),
    "/${local.database_name}"
  ) : format(
    "mysql://%s:%s@%s:%s/%s",
    google_sql_user.admin[0].name,
    local.db_password,
    google_sql_database_instance.mysql[0].private_ip_address,
    var.db_port,
    local.database_name
  )
  
  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_storage_bucket" "private" {
  name           = local.private_bucket_name
  location       = upper(var.region)
  storage_class  = var.storage_class
  force_destroy  = var.bucket_force_destroy

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = var.enable_versioning
  }

  lifecycle_rule {
    condition {
      age                = var.lifecycle_age_days
      num_newer_versions = 3
      with_state         = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 30
    }
    action {
      type = "Delete"
    }
  }

  dynamic "encryption" {
    for_each = var.bucket_encryption_key != null ? [1] : []
    content {
      default_kms_key_name = var.bucket_encryption_key
    }
  }

  labels = merge(
    local.common_labels,
    {
      component   = "storage"
      access_type = "private"
    }
  )
}

resource "google_storage_bucket" "public" {
  name          = local.public_bucket_name
  location      = upper(var.region)
  storage_class = var.storage_class
  force_destroy = var.bucket_force_destroy

  uniform_bucket_level_access = true

  website {
    main_page_suffix = var.website_main_page
    not_found_page   = var.website_error_page
  }

  cors {
    origin          = var.cors_origins
    method          = var.cors_methods
    response_header = var.cors_response_headers
    max_age_seconds = var.cors_max_age_seconds
  }

  labels = merge(
    local.common_labels,
    {
      component   = "storage"
      access_type = "public"
    }
  )
}

resource "google_storage_bucket_iam_member" "public_access" {
  count  = var.enable_public_bucket ? 1 : 0
  bucket = google_storage_bucket.public.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}
