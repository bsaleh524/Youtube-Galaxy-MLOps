terraform {
  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}

module "dev_project" {
  source       = "./modules/project-files"
  project_name = "youtube-galaxy"
  environment  = "dev"
  output_dir   = "./output/dev"
}

module "prod_project" {
  source       = "./modules/project-files"
  project_name = "youtube-galaxy"
  environment  = "prod"
  output_dir   = "./output/prod"
}

output "all_files_created" {
  description = "All files created across dev and prod"
  value       = concat(module.dev_project.files_created, module.prod_project.files_created)
}
