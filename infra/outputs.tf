output "server_public_ip" {
  description = "Add this as an A record in Hostinger for spookypharaoh.com"
  value       = module.oracle.server_public_ip
}

output "object_storage_bucket" {
  description = "Oracle Object Storage bucket name for artifacts"
  value       = module.oracle.bucket_name
}

output "object_storage_namespace" {
  description = "Oracle Object Storage namespace (needed for S3-compat endpoint)"
  value       = module.oracle.storage_namespace
}

output "s3_compat_endpoint" {
  description = "S3-compatible endpoint for Oracle Object Storage (use in boto3)"
  value       = module.oracle.s3_compat_endpoint
}

output "ssh_command" {
  description = "SSH into the server"
  value       = "ssh ubuntu@${module.oracle.server_public_ip}"
}
