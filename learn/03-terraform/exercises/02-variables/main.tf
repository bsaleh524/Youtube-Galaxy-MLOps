terraform {
  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}

variable "project_name" {
  description = "Name of the MLOps project"
  type        = string
  default     = "youtube-galaxy"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "features_enabled" {
  description = "Which features to enable"
  type        = list(string)
  default     = ["weaviate", "mlflow", "feast"]
}

locals {
  project_prefix = "${var.project_name}-${var.environment}"
  feature_list   = join(", ", var.features_enabled)
}

resource "local_file" "env_config" {
  filename = "${path.module}/output/${local.project_prefix}-config.txt"
  content  = <<-EOT
    Project:     ${var.project_name}
    Environment: ${var.environment}
    Prefix:      ${local.project_prefix}
    Features:    ${local.feature_list}
  EOT
}

output "config_file_path" {
  description = "Path to the generated config file"
  value       = local_file.env_config.filename
}

output "project_prefix" {
  description = "Project prefix used for naming cloud resources"
  value       = local.project_prefix
}
