/**
 * ============================================================================
 * PROVIDER CONFIGURATION
 * ============================================================================
 * Configures the Google Cloud Platform provider
 * ============================================================================
 */

provider "google" {
  credentials = file("terraform-sa.json")
  project     = var.project_id
  region      = var.region
}

