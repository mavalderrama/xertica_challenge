provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# ── Artifact Registry ────────────────────────────────────────────────────────
# Docker image repository for the compliance API.
# The deploy workflow pushes to: us-central1-docker.pkg.dev/<project>/compliance/api:<sha>
resource "google_artifact_registry_repository" "compliance" {
  provider      = google
  location      = var.region
  project       = var.project_id
  repository_id = "compliance"
  format        = "DOCKER"
  description   = "Compliance API Docker images"
}

# ── Secret Manager secrets ───────────────────────────────────────────────────
# Secret values are intentionally NOT set here (no secret_version resources).
# They must be populated manually or via a secrets management pipeline before
# the first deployment. This keeps sensitive values out of Terraform state.

resource "google_secret_manager_secret" "db_password" {
  secret_id = "compliance-db-password"
  project   = var.project_id
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "django_secret_key" {
  secret_id = "django-secret-key"
  project   = var.project_id
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "langfuse_public_key" {
  secret_id = "langfuse-public-key"
  project   = var.project_id
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "langfuse_secret_key" {
  secret_id = "langfuse-secret-key"
  project   = var.project_id
  replication {
    auto {}
  }
}

# ── Modules ──────────────────────────────────────────────────────────────────

module "gcs" {
  source      = "./modules/gcs"
  project_id  = var.project_id
  region      = var.region
  environment = var.environment
}

module "cloud_sql" {
  source      = "./modules/cloud_sql"
  project_id  = var.project_id
  region      = var.region
  environment = var.environment
  db_tier     = var.db_tier

  depends_on = [google_secret_manager_secret.db_password]
}

module "iam" {
  source     = "./modules/iam"
  project_id = var.project_id
}

module "cloud_run" {
  source             = "./modules/cloud_run"
  project_id         = var.project_id
  region             = var.region
  environment        = var.environment
  api_image          = var.api_image
  min_instances      = var.min_instances
  max_instances      = var.max_instances
  db_connection_name = module.cloud_sql.connection_name
  service_account    = module.iam.api_service_account_email
  gcs_bucket_name    = module.gcs.bucket_name
  langfuse_host      = var.langfuse_host
  allowed_hosts      = var.allowed_hosts
}
