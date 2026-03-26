variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "db_tier" {
  description = "Cloud SQL instance tier"
  type        = string
  default     = "db-g1-small"
}

variable "api_image" {
  description = "Docker image for the compliance API"
  type        = string
}

variable "min_instances" {
  description = "Cloud Run minimum instances"
  type        = number
  default     = 1
}

variable "max_instances" {
  description = "Cloud Run maximum instances"
  type        = number
  default     = 10
}
