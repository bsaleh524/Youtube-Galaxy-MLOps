# Module 03: Terraform

## What is Infrastructure as Code?

Without IaC, you provision servers by clicking around in a cloud console. This creates invisible, unreproducible infrastructure — you can't easily recreate it, version-control it, or share it with someone else.

**Terraform solves this.** You write `.tf` files describing the infrastructure you want (servers, storage, networks, IAM roles), and Terraform figures out what API calls to make to create it. Running `terraform apply` from scratch always produces the same result. `terraform destroy` tears it all down cleanly.

```
You write .tf files → terraform plan (preview changes) → terraform apply (make it real)
```

## Key Vocabulary

| Term | Meaning |
|---|---|
| **Provider** | A plugin that knows how to talk to a cloud API (AWS, Oracle, Hetzner, GitHub, etc.) |
| **Resource** | A single infrastructure object (`oci_objectstorage_bucket`, `aws_s3_bucket`) |
| **Data Source** | Read-only lookup of existing infrastructure (`data "aws_ami" "latest"`) |
| **Variable** | An input to your config (`var.region`, set in `terraform.tfvars`) |
| **Output** | A value exported after apply (e.g., the server's IP address) |
| **State** | Terraform's record of what it created. Lives in `terraform.tfstate`. **Never delete this.** |
| **Module** | A reusable group of resources (like a function in code) |
| **Plan** | A preview of what changes `apply` will make |

## The Core Workflow

```bash
terraform init        # download providers, initialize backend
terraform plan        # show what will be created/changed/destroyed
terraform apply       # actually do it (prompts for confirmation)
terraform destroy     # tear everything down
```

**State is critical.** Terraform's `.tfstate` file is the authoritative record of what Terraform created. If you delete a resource manually (via the cloud console), Terraform's state still shows it exists — next plan will try to create it again. Always use Terraform to manage what Terraform created.

---

## Setup (No Cloud Account Needed for Exercises 1–4)

These exercises use Terraform's `local` provider — creates files on your filesystem, no cloud credentials required. This teaches all the core concepts (resources, variables, outputs, state, modules) before you touch real cloud providers.

```bash
# Install Terraform (macOS)
brew tap hashicorp/tap
brew install hashicorp/tap/terraform

# Verify
terraform version
```

---

## Exercise 1: Your First Resource

**Goal:** Use Terraform to create a local file. Simple, but demonstrates the entire core workflow.

Create a new directory `exercises/01-local-file/` and add these files:

**`main.tf`**
```hcl
# The local provider creates files on your filesystem — no cloud needed
terraform {
  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}

# A "resource" describes one piece of infrastructure you want to exist
resource "local_file" "galaxy_config" {
  filename = "${path.module}/output/config.txt"
  content  = "Galaxy MLOps pipeline configuration\nCreated by Terraform"
}
```

```bash
cd exercises/01-local-file/
mkdir -p output

terraform init        # downloads the "local" provider
terraform plan        # shows: "+ local_file.galaxy_config will be created"
terraform apply       # creates the file (type "yes" when prompted)

cat output/config.txt  # verify the file exists
terraform destroy      # removes the file
```

**What to observe:**
- After `apply`, a `.terraform/` directory and `terraform.tfstate` appear — never delete these
- `terraform plan` shows `+` (create), `~` (change), `-` (destroy) symbols
- Running `terraform apply` twice does nothing — the resource already matches desired state

---

## Exercise 2: Variables and Outputs

Variables make configs reusable. Outputs expose values after apply (like a function's return value).

**`exercises/02-variables/main.tf`**
```hcl
terraform {
  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}

# Input variables — callers provide these
variable "project_name" {
  description = "Name of the MLOps project"
  type        = string
  default     = "youtube-galaxy"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  # No default — required input
  # Set in terraform.tfvars or via -var flag
}

variable "features_enabled" {
  description = "Which features to enable"
  type        = list(string)
  default     = ["weaviate", "mlflow", "feast"]
}

# Local values — computed from inputs, avoid repetition
locals {
  project_prefix = "${var.project_name}-${var.environment}"
  feature_list   = join(", ", var.features_enabled)
}

# Resource using variables
resource "local_file" "env_config" {
  filename = "${path.module}/output/${local.project_prefix}-config.txt"
  content  = <<-EOT
    Project: ${var.project_name}
    Environment: ${var.environment}
    Prefix: ${local.project_prefix}
    Features: ${local.feature_list}
  EOT
}

# Outputs — visible after apply, usable by other modules
output "config_file_path" {
  description = "Path to the generated config file"
  value       = local_file.env_config.filename
}

output "project_prefix" {
  description = "Project prefix used for naming resources"
  value       = local.project_prefix
}
```

**`exercises/02-variables/terraform.tfvars`**
```hcl
# Variables that differ per environment go here
# This file is gitignored in production (contains secrets)
environment = "dev"
project_name = "youtube-galaxy"
```

```bash
cd exercises/02-variables/
mkdir -p output

terraform init
terraform apply   # reads terraform.tfvars automatically

# Override a variable on the command line
terraform apply -var="environment=prod"

# After apply, outputs are shown:
# config_file_path = "./output/youtube-galaxy-dev-config.txt"
# project_prefix   = "youtube-galaxy-dev"

# Access outputs anytime
terraform output project_prefix
```

---

## Exercise 3: State and the Danger of Manual Changes

This exercise demonstrates why you should never manually edit infrastructure that Terraform manages.

```bash
cd exercises/01-local-file/
terraform apply     # ensure the file exists

# Manually delete the file (simulating a human clicking "delete" in a cloud console)
rm output/config.txt

# Terraform's state still says the file exists
terraform plan      # shows: file will be RECREATED (state diverged from reality)

# Terraform corrects the drift on next apply
terraform apply     # recreates the file
```

**The lesson:** Terraform is the source of truth. If you change something outside Terraform, the state file becomes wrong. On next apply, Terraform will try to "correct" your manual change — often unexpectedly. Always use Terraform to change what Terraform created.

For the Galaxy project, this means: never create the Oracle instance or S3 bucket via the cloud console. Always go through `terraform apply`.

---

## Exercise 4: Modules (Reusable Infrastructure)

Modules are like functions: they encapsulate a set of resources and take inputs/outputs. The Galaxy project's `infra/` directory uses modules to separate Oracle Cloud and AWS configuration.

**Directory structure:**
```
exercises/04-modules/
├── main.tf              ← root module (calls the submodule)
└── modules/
    └── project-files/
        ├── main.tf      ← submodule definition
        ├── variables.tf
        └── outputs.tf
```

**`exercises/04-modules/modules/project-files/variables.tf`**
```hcl
variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "output_dir" {
  type    = string
  default = "./output"
}
```

**`exercises/04-modules/modules/project-files/main.tf`**
```hcl
resource "local_file" "readme" {
  filename = "${var.output_dir}/${var.project_name}-${var.environment}-readme.txt"
  content  = "Project: ${var.project_name} | Env: ${var.environment}"
}

resource "local_file" "config" {
  filename = "${var.output_dir}/${var.project_name}-${var.environment}-config.txt"
  content  = "Auto-generated by Terraform module"
}
```

**`exercises/04-modules/modules/project-files/outputs.tf`**
```hcl
output "files_created" {
  value = [local_file.readme.filename, local_file.config.filename]
}
```

**`exercises/04-modules/main.tf`**
```hcl
terraform {
  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}

# Call the module twice — once for dev, once for prod
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

output "all_files" {
  value = concat(module.dev_project.files_created, module.prod_project.files_created)
}
```

```bash
cd exercises/04-modules/
mkdir -p output/dev output/prod

terraform init    # note: downloads provider and initializes modules
terraform apply
terraform output  # see all_files: 4 files across dev and prod
```

---

## Exercise 5: Oracle Cloud (Real Infrastructure)

The Galaxy project's actual Terraform config. **Requires an Oracle Cloud account** — sign up for the Always Free tier.

Preview of `infra/modules/oracle/compute.tf`:

```hcl
# The Oracle Cloud provider
terraform {
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
  }
}

provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region  # e.g., "us-phoenix-1"
}

# The A1 Flex instance (Always Free ARM VM)
resource "oci_core_instance" "galaxy_server" {
  compartment_id      = var.compartment_id
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "galaxy-mlops-server"
  shape               = "VM.Standard.A1.Flex"     # ARM Always Free

  shape_config {
    ocpus         = 4
    memory_in_gbs = 24
  }

  # k3s bootstrap script runs on first boot
  metadata = {
    user_data = base64encode(file("${path.module}/user_data.sh"))
    ssh_authorized_keys = file(var.ssh_public_key_path)
  }

  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.ubuntu_arm.images[0].id
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.galaxy_subnet.id
    assign_public_ip = true
  }
}

output "server_public_ip" {
  value = oci_core_instance.galaxy_server.public_ip
  description = "Point your Hostinger A record to this IP"
}
```

After `terraform apply`:
1. Note the `server_public_ip` in the output
2. SSH in: `ssh ubuntu@<ip>`
3. k3s should be running: `kubectl get nodes`
4. Point Hostinger DNS: A record `spookypharaoh.com` → this IP

---

## How Terraform Maps to the Galaxy Project

```
infra/
├── main.tf                     ← calls oracle and (optionally) aws modules
├── variables.tf                ← all input variables
├── outputs.tf                  ← server IP, bucket names, etc.
├── terraform.tfvars.example    ← template (never commit real tfvars)
└── modules/
    ├── oracle/
    │   ├── compute.tf          ← A1 Flex instance + k3s user_data
    │   ├── storage.tf          ← Object Storage bucket (S3-compatible)
    │   ├── network.tf          ← VCN, subnet, internet gateway
    │   ├── security.tf         ← Security list: allow 80, 443, 22, 6443
    │   └── user_data.sh        ← k3s install + kubeconfig setup
    └── aws/ (optional)
        ├── s3.tf               ← Artifact bucket for SageMaker learning exercise
        ├── iam.tf              ← SageMaker execution role
        └── ecr.tf              ← Container registry
```

The `output "server_public_ip"` value is what you put in Hostinger → DNS → A record.

## Summary

| Command | What it does |
|---|---|
| `terraform init` | Download providers, initialize backend |
| `terraform plan` | Preview changes without applying |
| `terraform apply` | Create/update infrastructure |
| `terraform destroy` | Remove all managed infrastructure |
| `terraform output` | Show output values |
| `terraform state list` | List resources in state |
| `terraform import` | Adopt existing infrastructure into state |
