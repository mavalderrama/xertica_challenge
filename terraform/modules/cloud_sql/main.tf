variable "project_id" {}
variable "region" {}
variable "environment" {}
variable "db_tier" {}

resource "google_sql_database_instance" "main" {
  name             = "compliance-db-${var.environment}"
  database_version = "POSTGRES_16"
  region           = var.region
  project          = var.project_id

  settings {
    tier = var.db_tier

    # Enable pgvector extension — required for dense embedding storage and
    # cosine similarity search (used by VectorStoreRetriever).
    database_flags {
      name  = "cloudsql.enable_pgvector"
      value = "on"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }

    ip_configuration {
      # No public IP — Cloud Run connects via the Cloud SQL Auth Proxy Unix socket.
      ipv4_enabled    = false
      private_network = "projects/${var.project_id}/global/networks/default"
    }
  }

  deletion_protection = true
}

resource "google_sql_database" "compliance" {
  name     = "compliance_db"
  instance = google_sql_database_instance.main.name
  project  = var.project_id
}

# Database user — password is pulled from Secret Manager so it is never
# stored in Terraform state in plaintext.
resource "google_sql_user" "compliance" {
  name     = "compliance"
  instance = google_sql_database_instance.main.name
  project  = var.project_id
  password = data.google_secret_manager_secret_version.db_password.secret_data
}

data "google_secret_manager_secret_version" "db_password" {
  secret  = "compliance-db-password"
  version = "latest"
  project = var.project_id
}

output "connection_name" {
  value = google_sql_database_instance.main.connection_name
}
