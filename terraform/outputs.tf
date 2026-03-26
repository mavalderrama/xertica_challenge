output "api_url" {
  description = "Cloud Run service URL"
  value       = module.cloud_run.service_url
}

output "db_connection_name" {
  description = "Cloud SQL connection name"
  value       = module.cloud_sql.connection_name
}

output "gcs_bucket_name" {
  description = "GCS bucket name for compliance documents"
  value       = module.gcs.bucket_name
}

output "api_service_account_email" {
  description = "Service account email for the API"
  value       = module.iam.api_service_account_email
}
