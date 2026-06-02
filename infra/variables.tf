variable "tenancy_ocid" {
  description = "Your Oracle Cloud tenancy OCID (found in OCI Console → Profile → Tenancy)"
  type        = string
}

variable "user_ocid" {
  description = "Your Oracle Cloud user OCID"
  type        = string
}

variable "fingerprint" {
  description = "Fingerprint of your OCI API signing key"
  type        = string
}

variable "private_key_path" {
  description = "Path to your OCI API private key file"
  type        = string
  default     = "~/.oci/oci_api_key.pem"
}

variable "region" {
  description = "OCI region (e.g. us-phoenix-1, us-ashburn-1)"
  type        = string
  default     = "us-phoenix-1"
}

variable "compartment_ocid" {
  description = "OCI compartment to deploy into (use root tenancy OCID for personal accounts)"
  type        = string
}

variable "ssh_public_key_path" {
  description = "Path to your SSH public key for instance access"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "project_name" {
  description = "Prefix for all named resources"
  type        = string
  default     = "galaxy"
}
