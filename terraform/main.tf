provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

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
}

module "iam" {
  source     = "./modules/iam"
  project_id = var.project_id
}

module "cloud_run" {
  source              = "./modules/cloud_run"
  project_id          = var.project_id
  region              = var.region
  environment         = var.environment
  api_image           = var.api_image
  min_instances       = var.min_instances
  max_instances       = var.max_instances
  db_connection_name  = module.cloud_sql.connection_name
  service_account     = module.iam.api_service_account_email
  gcs_bucket_name     = module.gcs.bucket_name
}
