resource "oci_core_vcn" "galaxy_vcn" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.project_name}-vcn"
  cidr_blocks    = ["10.0.0.0/16"]
  dns_label      = "${var.project_name}vcn"
}

resource "oci_core_internet_gateway" "galaxy_igw" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.galaxy_vcn.id
  display_name   = "${var.project_name}-igw"
  enabled        = true
}

resource "oci_core_route_table" "galaxy_rt" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.galaxy_vcn.id
  display_name   = "${var.project_name}-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.galaxy_igw.id
  }
}

resource "oci_core_security_list" "galaxy_sl" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.galaxy_vcn.id
  display_name   = "${var.project_name}-sl"

  # Allow all outbound
  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  # SSH
  ingress_security_rules {
    protocol = "6" # TCP
    source   = "0.0.0.0/0"
    tcp_options { min = 22; max = 22 }
  }

  # HTTP
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options { min = 80; max = 80 }
  }

  # HTTPS
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options { min = 443; max = 443 }
  }

  # k3s API server (for kubectl from your laptop)
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options { min = 6443; max = 6443 }
  }
}

resource "oci_core_subnet" "galaxy_subnet" {
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.galaxy_vcn.id
  display_name      = "${var.project_name}-subnet"
  cidr_block        = "10.0.1.0/24"
  dns_label         = "${var.project_name}sub"
  route_table_id    = oci_core_route_table.galaxy_rt.id
  security_list_ids = [oci_core_security_list.galaxy_sl.id]
}
