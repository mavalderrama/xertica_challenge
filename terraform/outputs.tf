output "api_url" {
  description = "Public URL of the deployed Cloud Run compliance API."
  value       = module.cloud_run.service_url
}

output "db_connection_name" {
  description = "Cloud SQL connection name used by the Cloud SQL Auth Proxy (format: project:region:instance)."
  value       = module.cloud_sql.connection_name
}

output "gcs_bucket_name" {
  description = "Name of the GCS bucket used for customer compliance documents."
  value       = module.gcs.bucket_name
}

output "api_service_account_email" {
  description = "Email of the least-privilege service account attached to the Cloud Run service."
  value       = module.iam.api_service_account_email
}

output "artifact_registry_url" {
  description = "Base URL for the Artifact Registry Docker repository. Tag images as <url>/api:<sha>."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.compliance.repository_id}"
}
