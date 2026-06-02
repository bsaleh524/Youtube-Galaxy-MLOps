terraform {
  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}

resource "local_file" "galaxy_config" {
  filename = "${path.module}/output/config.txt"
  content  = "Galaxy MLOps pipeline configuration\nCreated by Terraform"
}
