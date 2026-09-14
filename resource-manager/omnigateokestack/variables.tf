# Every variable here is a Resource Manager "choice" -- grouping/labels/sensitivity live in
# schema.yaml, not here (ORM overlays that onto this list; Terraform itself doesn't read it).

variable "compartment_ocid" {
  description = "Compartment to create the OKE cluster, network, and node pool in."
  type        = string
}

variable "region" {
  description = "OCI region to deploy into, e.g. us-ashburn-1."
  type        = string
}

# --- Application config -------------------------------------------------------------------

variable "omnigate_llm_api_key" {
  description = "Anthropic API key (console.anthropic.com) for NL2SQL. Without it the gateway still deploys but can't translate English to SQL."
  type        = string
  sensitive   = true
  default     = ""
}

variable "omnigate_llm_model" {
  description = "Anthropic model id used for NL2SQL."
  type        = string
  default     = "claude-sonnet-5"
}

variable "omnigate_app_username" {
  description = "Ask-app login username. Required -- refusing to ship the repo's well-known demo/demo login on a public LoadBalancer."
  type        = string
  default     = "demo"
}

variable "omnigate_app_password" {
  description = "Ask-app login password, plain text. Hashed automatically during apply (see password-hash.tf) using the same PasswordHash utility bundled in the deployed image -- no local Docker or manual hash generation needed."
  type        = string
  sensitive   = true
}

variable "expose_wire_protocols" {
  description = "Also expose the Oracle/Postgres/MySQL wire-protocol ports (1521/5433/3306) via a second public LoadBalancer, in addition to the HTTP admin console/Ask app on 8080. Off by default -- these protocols carry their own auth per connection, but there's no reason to expose them publicly unless you actually plan to connect a wire-protocol client from outside the cluster."
  type        = bool
  default     = false
}

# --- Image ----------------------------------------------------------------------------------

variable "image_repository" {
  description = "Fully-qualified OCIR path for the omnigate image. Defaults to the publisher's own pre-built image -- Marketplace deployers should not need to build anything themselves."
  type        = string
  default     = "ocir.us-phoenix-1.oci.oraclecloud.com/ax8tpjdxhykk/omnigate"
}

variable "image_tag" {
  description = "Image tag to deploy."
  type        = string
  default     = "latest"
}

# --- Compute sizing (Always Free: VM.Standard.A1.Flex, Ampere) ------------------------------

variable "node_pool_size" {
  description = "Number of worker nodes."
  type        = number
  default     = 1
}

variable "node_ocpus" {
  description = "OCPUs per node (VM.Standard.A1.Flex). Always Free tenancies get a limited Ampere A1 allocation shared across the whole account -- check Governance & Administration > Limits in the Console before raising this beyond the default."
  type        = number
  default     = 2
}

variable "node_memory_gb" {
  description = "Memory (GB) per node (VM.Standard.A1.Flex)."
  type        = number
  default     = 12
}

variable "node_boot_volume_gb" {
  description = "Boot volume size (GB) per node. The omnigate image itself is a few GB (bundles a compiled llama-server + a local embedding model), so the default here is larger than a bare-minimum node."
  type        = number
  default     = 50
}

# --- Storage ---------------------------------------------------------------------------------

variable "postgres_storage_gb" {
  description = "Block Volume size for the seeded Postgres backend."
  type        = number
  default     = 5
}

variable "omnigate_data_storage_gb" {
  description = "Block Volume size for OmniGate's own ConfigStore (admin-set config, e.g. an API key entered live in the UI -- this is what needs to survive a pod restart)."
  type        = number
  default     = 2
}
