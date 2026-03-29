variable "project_id" {
  description = "GCP project ID where all resources will be created."
  type        = string
}

variable "region" {
  description = "GCP region for all resources. Must be us-central1 to satisfy data-residency constraint."
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Deployment environment: dev, staging, or prod. Used to suffix resource names."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "db_tier" {
  description = "Cloud SQL machine tier. db-g1-small is sufficient for dev/staging; use db-custom-2-7680 for prod."
  type        = string
  default     = "db-g1-small"
}

variable "api_image" {
  description = "Full Docker image URI for the compliance API, e.g. us-central1-docker.pkg.dev/<project>/compliance/api:<sha>"
  type        = string
}

variable "min_instances" {
  description = "Minimum number of Cloud Run instances. Set to 1 to avoid cold starts on the first alert after inactivity."
  type        = number
  default     = 1
}

variable "max_instances" {
  description = "Maximum number of Cloud Run instances. Caps cost at peak alert volume."
  type        = number
  default     = 10
}

variable "langfuse_host" {
  description = "URL of the Langfuse observability server, e.g. https://cloud.langfuse.com or a self-hosted URL."
  type        = string
  default     = "https://cloud.langfuse.com"
}

variable "allowed_hosts" {
  description = "Comma-separated hostnames Django will accept. Include the Cloud Run service URL after first deploy."
  type        = string
  # Populate after first deploy: gcloud run services describe compliance-api --format='value(status.url)'
  default     = ""
}
