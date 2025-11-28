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
  
  private_bucket_name = var.is_sub_hospital ? "${local.parent_uuid_underscore}_private_${var.environment}" : "${local.cluster_uuid_underscore}_private_${var.environment}"
  public_bucket_name  = var.is_sub_hospital ? "${local.parent_uuid_underscore}_public_${var.environment}" : "${local.cluster_uuid_underscore}_public_${var.environment}"
}

resource "random_string" "special_char" {
  length  = 1
  special = true
  upper   = false
  lower   = false
  numeric = false
  override_special = "@#$%&*!-_"

  lifecycle {
    ignore_changes = all
  }
}

resource "random_integer" "password_number" {
  min = 1000
  max = 9999

  lifecycle {
    ignore_changes = all
  }
}

locals {
  db_password = "medicalcircle${random_string.special_char.result}${random_integer.password_number.result}"
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

data "google_storage_bucket" "parent_private" {
  count   = var.is_sub_hospital ? 1 : 0
  name    = local.private_bucket_name
}

resource "google_storage_bucket_object" "cluster_db_sql" {
  count  = var.is_sub_hospital ? 0 : 1
  name   = "database-init/${var.cluster_uuid}/ClusterDB.sql"
  bucket = google_storage_bucket.private[0].name
  source = "${path.module}/sql/ClusterDB.sql"
}

resource "google_storage_bucket_object" "sn_tables_sql" {
  name   = "database-init/${var.cluster_uuid}/sn_tables.sql"
  bucket = var.is_sub_hospital ? data.google_storage_bucket.parent_private[0].name : google_storage_bucket.private[0].name
  source = "${path.module}/sql/sn_tables.sql"
}

resource "google_storage_bucket_object" "init_script" {
  name    = "database-init/${var.cluster_uuid}/init.sh"
  bucket  = var.is_sub_hospital ? data.google_storage_bucket.parent_private[0].name : google_storage_bucket.private[0].name
  content = templatefile("${path.module}/scripts/init_database.sh", {
    db_host          = var.is_sub_hospital ? data.google_sql_database_instance.parent[0].private_ip_address : google_sql_database_instance.mysql[0].private_ip_address
    db_user          = var.is_sub_hospital ? var.db_user : google_sql_user.admin[0].name
    db_password      = var.is_sub_hospital ? "" : local.db_password
    db_name          = google_sql_database.database.name
    bucket_name      = var.is_sub_hospital ? data.google_storage_bucket.parent_private[0].name : google_storage_bucket.private[0].name
    cluster_uuid     = var.cluster_uuid
    is_sub_hospital  = var.is_sub_hospital ? "true" : "false"
    project_id       = var.project_id
    parent_instance_name = var.is_sub_hospital ? var.parent_instance_name : ""
    parent_uuid      = var.is_sub_hospital ? replace(replace(var.parent_instance_name, "mc-cluster-", ""), "-", "_") : ""
  })

  depends_on = [
    google_storage_bucket_object.sn_tables_sql
  ]
}

resource "null_resource" "database_init" {
  count = var.init_vm_name != "" ? 1 : 0
  
  triggers = {
    database_id      = google_sql_database.database.id
    init_script_id   = google_storage_bucket_object.init_script.id
    cluster_uuid     = var.cluster_uuid
    is_sub_hospital  = var.is_sub_hospital ? "true" : "false"
    db_name          = google_sql_database.database.name
    sn_tables_id     = google_storage_bucket_object.sn_tables_sql.id
    cluster_db_id    = var.is_sub_hospital ? "" : google_storage_bucket_object.cluster_db_sql[0].id
  }

  provisioner "local-exec" {
    command = <<-EOT
      BUCKET_NAME="${var.is_sub_hospital ? data.google_storage_bucket.parent_private[0].name : google_storage_bucket.private[0].name}"
      INIT_SCRIPT="gs://$${BUCKET_NAME}/database-init/${var.cluster_uuid}/init.sh"
      
      echo "=========================================="
      echo "Database Initialization Starting"
      echo "Hospital UUID: ${var.cluster_uuid}"
      echo "Is Sub-Hospital: ${var.is_sub_hospital ? "true" : "false"}"
      echo "Database Name: ${google_sql_database.database.name}"
      echo "Bucket: $${BUCKET_NAME}"
      echo "=========================================="
      
      if ! command -v gcloud &> /dev/null; then
        echo "WARNING: gcloud not found. Database initialization will be skipped."
        echo "Please run the initialization manually using:"
        echo "  gcloud compute ssh ${var.init_vm_name} --zone=${var.region}-a --project=${var.project_id} --command='gsutil cp $${INIT_SCRIPT} /tmp/init-${var.cluster_uuid}.sh && chmod +x /tmp/init-${var.cluster_uuid}.sh && sudo /tmp/init-${var.cluster_uuid}.sh'"
        exit 0
      fi
      
      echo "Waiting for database to be ready..."
      sleep 15
      
      echo "Copying and executing initialization script..."
      if gcloud compute ssh ${var.init_vm_name} \
        --zone=${var.region}-a \
        --project=${var.project_id} \
        --command="gsutil cp $${INIT_SCRIPT} /tmp/init-${var.cluster_uuid}.sh && chmod +x /tmp/init-${var.cluster_uuid}.sh && sudo /tmp/init-${var.cluster_uuid}.sh" 2>&1; then
        echo "Database initialization completed successfully"
      else
        echo "WARNING: Database initialization failed. This is non-critical."
        echo "Database and infrastructure are created. You can initialize tables manually later."
        echo "Manual initialization command:"
        echo "  gcloud compute ssh ${var.init_vm_name} --zone=${var.region}-a --project=${var.project_id} --command='gsutil cp $${INIT_SCRIPT} /tmp/init-${var.cluster_uuid}.sh && chmod +x /tmp/init-${var.cluster_uuid}.sh && sudo /tmp/init-${var.cluster_uuid}.sh'"
        exit 0
      fi
    EOT
  }

  depends_on = [
    google_sql_database.database,
    google_storage_bucket_object.init_script,
    google_storage_bucket_object.sn_tables_sql
  ]
}

resource "google_secret_manager_secret" "db_uri" {
  count     = var.is_sub_hospital ? 0 : 1
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

data "google_secret_manager_secret_version" "parent_db_uri" {
  count   = var.is_sub_hospital ? 1 : 0
  secret  = "${replace(replace(var.parent_instance_name, "mc-cluster-", ""), "-", "_")}_DATABASE_URI"
  project = var.project_id
}

resource "google_secret_manager_secret_version" "db_uri" {
  count     = var.is_sub_hospital ? 0 : 1
  secret    = google_secret_manager_secret.db_uri[0].id
  secret_data = format(
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
  count          = var.is_sub_hospital ? 0 : 1
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
  count         = var.is_sub_hospital ? 0 : 1
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
  count  = var.is_sub_hospital ? 0 : (var.enable_public_bucket ? 1 : 0)
  bucket = google_storage_bucket.public[0].name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}
