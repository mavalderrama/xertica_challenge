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

    database_flags {
      name  = "cloudsql.enable_pgvector"
      value = "on"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }

    ip_configuration {
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

output "connection_name" {
  value = google_sql_database_instance.main.connection_name
}
