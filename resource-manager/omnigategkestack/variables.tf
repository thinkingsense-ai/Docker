# Every variable here is meant to become a Cloud Shell tutorial prompt (see tutorial.md) the same
# way the OCI stack's variables.tf feeds Resource Manager's schema.yaml -- there's no GCP
# equivalent of that schema-driven Console form (see README's "Why no schema.yaml" section), so
# grouping/help text live only here and in tutorial.md instead.

variable "gcp_project_id" {
  description = "GCP project to create the cluster, network, and node pool in. Must already exist and be linked to a billing account."
  type        = string
}

variable "gcp_region" {
  description = "GCP region for the whole stack, e.g. us-central1."
  type        = string
  default     = "us-central1"
}

variable "gcp_zone_suffix" {
  description = "Zone suffix appended to gcp_region for the GKE cluster's location, e.g. \"a\" for us-central1-a. A zonal (not regional) cluster is deliberate -- see gke.tf."
  type        = string
  default     = "a"
}

# --- Application config -------------------------------------------------------------------

variable "omnigate_llm_api_key" {
  description = "Anthropic API key (console.anthropic.com) for NL2SQL -- required, since a stack applied without one deploys fine but can't answer any question."
  type        = string
  sensitive   = true
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
  description = "Fully-qualified Artifact Registry path for the omnigate image. Defaults to the publisher's own pre-built image -- deployers should not need to build anything themselves."
  type        = string
  default     = "us-docker.pkg.dev/thinkingsense/omnigate/omnigate"
}

variable "image_tag" {
  description = "Image tag to deploy."
  type        = string
  default     = "latest"
}

# --- Compute sizing ---------------------------------------------------------------------------
# Unlike OCI's Always Free Ampere A1 allocation, GCP has no free compute shape generous enough to
# actually run this (its free tier is one e2-micro, nowhere near the omnigate container's own 1
# vCPU / 1Gi request). These defaults are a modest, real-money size, not a free one -- said
# plainly rather than implied by an "Always Free"-style comment the way the OCI stack's has.

variable "node_pool_size" {
  description = "Number of worker nodes."
  type        = number
  default     = 1
}

variable "node_machine_type" {
  description = "Machine type for the node pool. t2a-standard-2 (2 vCPU / 8GB, Ampere/arm64) -- confirmed live: the published omnigate image is arm64-only (no amd64 manifest), same reason the AWS stack deliberately runs Graviton/arm64 EKS nodes (see omnigateeksstack/README.md) instead of a default x86 node group. An e2-* (amd64) node pool here fails every pod with ErrImagePull/\"no match for platform in manifest\"."
  type        = string
  default     = "t2a-standard-2"
}

variable "node_boot_disk_gb" {
  description = "Boot disk size (GB) per node. The omnigate image itself is a few GB (bundles a compiled llama-server + a local embedding model), so the default here is larger than a bare-minimum node."
  type        = number
  default     = 50
}

# --- Storage ---------------------------------------------------------------------------------

variable "postgres_storage_gb" {
  description = "Persistent Disk size for the seeded Postgres backend."
  type        = number
  default     = 5
}

variable "omnigate_data_storage_gb" {
  description = "Persistent Disk size for OmniGate's own ConfigStore (admin-set config, e.g. an API key entered live in the UI -- this is what needs to survive a pod restart)."
  type        = number
  default     = 2
}
