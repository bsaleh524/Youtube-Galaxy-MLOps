terraform {
  required_version = ">= 1.5"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
  }
  # Uncomment to store state in Oracle Object Storage instead of local file:
  # backend "s3" {
  #   bucket   = "galaxy-terraform-state"
  #   key      = "terraform.tfstate"
  #   endpoint = "https://<namespace>.compat.objectstorage.<region>.oraclecloud.com"
  #   region   = "us-phoenix-1"
  #   skip_credentials_validation = true
  #   skip_metadata_api_check     = true
  #   force_path_style            = true
  # }
}

provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}

module "oracle" {
  source = "./modules/oracle"

  tenancy_ocid        = var.tenancy_ocid
  compartment_ocid    = var.compartment_ocid
  region              = var.region
  ssh_public_key_path = var.ssh_public_key_path
  project_name        = var.project_name
}
