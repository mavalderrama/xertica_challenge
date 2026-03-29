variable "project_id" {}
variable "region" {}
variable "environment" {}
variable "api_image" {}
variable "min_instances" {}
variable "max_instances" {}
variable "db_connection_name" {}
variable "service_account" {}
variable "gcs_bucket_name" {}
variable "langfuse_host" {}
variable "allowed_hosts" {}

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

      # Expose port 8000 — matches the Dockerfile CMD (uvicorn --port 8000).
      # Cloud Run defaults to 8080; without this, health checks fail.
      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      # ── Non-secret environment variables ─────────────────────────────────
      env {
        name  = "DJANGO_SETTINGS_MODULE"
        value = "config.settings.production"
      }

      # Cloud SQL Auth Proxy mounts the Unix socket at /cloudsql/<connection_name>.
      # Django's psycopg2 treats a path starting with "/" as a Unix socket host.
      env {
        name  = "POSTGRES_HOST"
        value = "/cloudsql/${var.db_connection_name}"
      }

      env {
        name  = "POSTGRES_DB"
        value = "compliance_db"
      }

      env {
        name  = "POSTGRES_USER"
        value = "compliance"
      }

      env {
        name  = "POSTGRES_PORT"
        value = "5432"
      }

      env {
        name  = "GCS_BUCKET_NAME"
        value = var.gcs_bucket_name
      }

      # Use Vertex AI (Gemini) in production — satisfies GCP data-residency constraint.
      env {
        name  = "LLM_PROVIDER"
        value = "vertexai"
      }

      env {
        name  = "GEMINI_MODEL"
        value = "gemini-2.0-flash-001"
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "GCP_LOCATION"
        value = var.region
      }

      env {
        name  = "LANGFUSE_HOST"
        value = var.langfuse_host
      }

      # Cloud Run auto-injects the service URL as CLOUD_RUN_URL; use a variable
      # for ALLOWED_HOSTS so the Django production settings can accept requests.
      env {
        name  = "ALLOWED_HOSTS"
        value = var.allowed_hosts
      }

      env {
        name  = "USE_MOCK_BQ"
        value = "false"
      }

      env {
        name  = "USE_MOCK_GCS"
        value = "false"
      }

      # ── Secret environment variables (from Secret Manager) ────────────────
      env {
        name = "POSTGRES_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = "compliance-db-password"
            version = "latest"
          }
        }
      }

      env {
        name = "DJANGO_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = "django-secret-key"
            version = "latest"
          }
        }
      }

      env {
        name = "LANGFUSE_PUBLIC_KEY"
        value_source {
          secret_key_ref {
            secret  = "langfuse-public-key"
            version = "latest"
          }
        }
      }

      env {
        name = "LANGFUSE_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = "langfuse-secret-key"
            version = "latest"
          }
        }
      }

      # Mount the Cloud SQL Unix socket into the container filesystem.
      # The socket appears at /cloudsql/<connection_name>/.s.PGSQL.5432
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }

    # Declare the Cloud SQL volume — the Auth Proxy sidecar is managed by Cloud Run.
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
