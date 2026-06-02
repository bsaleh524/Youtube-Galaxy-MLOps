data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "galaxy_artifacts" {
  compartment_id = var.compartment_ocid
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  name           = "${var.project_name}-artifacts"
  access_type    = "NoPublicAccess"
  storage_tier   = "Standard"

  # Enable versioning so we can recover old Parquet files
  versioning = "Enabled"
}
