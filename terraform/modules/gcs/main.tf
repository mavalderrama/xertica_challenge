variable "project_id" {}
variable "region" {}
variable "environment" {}

resource "google_storage_bucket" "compliance_docs" {
  name          = "compliance-docs-${var.project_id}-${var.environment}"
  location      = var.region
  project       = var.project_id
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
}

output "bucket_name" {
  value = google_storage_bucket.compliance_docs.name
}
