/**
 * ============================================================================
 * PROVIDER CONFIGURATION
 * ============================================================================
 * Configures the Google Cloud Platform provider
 * Supports both file-based credentials and default credentials (Cloud Run)
 * ============================================================================
 */

provider "google" {
  # Use credentials file if provided, otherwise Terraform will use default credentials (Cloud Run service account)
  # try() handles case where file doesn't exist - falls back to null which means use default credentials
  credentials = var.credentials_path != null && var.credentials_path != "" ? try(file(var.credentials_path), null) : null
  project     = var.project_id
  region      = var.region
}

