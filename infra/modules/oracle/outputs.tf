output "server_public_ip" {
  value = oci_core_instance.galaxy_server.public_ip
}

output "bucket_name" {
  value = oci_objectstorage_bucket.galaxy_artifacts.name
}

output "storage_namespace" {
  value = data.oci_objectstorage_namespace.ns.namespace
}

output "s3_compat_endpoint" {
  value = "https://${data.oci_objectstorage_namespace.ns.namespace}.compat.objectstorage.${var.region}.oraclecloud.com"
}
