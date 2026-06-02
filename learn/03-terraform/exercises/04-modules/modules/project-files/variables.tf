variable "project_name" {
  type        = string
  description = "Name of the project"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
}

variable "output_dir" {
  type        = string
  description = "Directory to write files into"
  default     = "./output"
}
