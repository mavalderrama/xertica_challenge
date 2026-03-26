variable "project_id" {}
variable "region" {}
variable "environment" {}
variable "api_image" {}
variable "min_instances" {}
variable "max_instances" {}
variable "db_connection_name" {}
variable "service_account" {}
variable "gcs_bucket_name" {}

resource "google_cloud_run_v2_service" "api" {
  name     = "compliance-api-${var.environment}"
  location = var.region
  project  = var.project_id

  template {
    service_account = var.service_account

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.api_image

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      env {
        name  = "DJANGO_SETTINGS_MODULE"
        value = "config.settings.production"
      }

      env {
        name  = "GCS_BUCKET_NAME"
        value = var.gcs_bucket_name
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [var.db_connection_name]
      }
    }
  }
}

output "service_url" {
  value = google_cloud_run_v2_service.api.uri
}
