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

# --- High availability / multi-node ---------------------------------------------------------
# See helm/omnigate/values.yaml's own omnigate.configDb comment for the real reasoning: raising
# omnigate_replica_count alone (with the config-DB variables left empty) leaves every replica
# beyond the first crash-looping on a PVC only one pod can mount -- both must be set together.

variable "omnigate_replica_count" {
  description = "Number of OmniGate pods behind the NLB Service, for high availability / horizontal scale. Leave at 1 unless omnigate_config_db_url is also set (see that variable) -- more than one replica needs a shared, externally-provisioned config database, not the default per-pod local volume."
  type        = number
  default     = 1
}

variable "omnigate_config_db_url" {
  description = "A real, separately-provisioned Postgres JDBC URL (e.g. jdbc:postgresql://your-managed-db-host:5432/omnigate_config) that every OmniGate replica shares for its admin-editable config store. Required when omnigate_replica_count > 1; leave blank for a single-replica deployment (the default free-tier setup, which uses a local per-pod volume instead)."
  type        = string
  default     = ""
}

variable "omnigate_config_db_user" {
  description = "Username for omnigate_config_db_url. Required when omnigate_replica_count > 1."
  type        = string
  default     = ""
}

variable "omnigate_config_db_adb_ocid" {
  description = "Optional. OCID of the Autonomous Database behind omnigate_config_db_url. When set, this stack adds its worker nodes' public IPs to that database's IP access list before the pods start (and on every scale-up), and removes them again on destroy. Leave blank to manage the ACL yourself; blank is also right if the database is open to all IPs or on a private endpoint (this stack won't touch an ADB that has no IP ACL)."
  type        = string
  default     = ""
}

variable "omnigate_config_db_password" {
  description = "Password for omnigate_config_db_url. Required when omnigate_replica_count > 1."
  type        = string
  default     = ""
  sensitive   = true
}

# --- Admin API access (optional) -----------------------------------------------------------

variable "omnigate_admin_api_token" {
  description = "Optional bearer token (any long random string) that grants admin-role access to the admin API, so scripts such as the test harness can call /api/query without a browser sign-in. Setting it switches admin authentication on. Blank leaves authentication as configured elsewhere. Note that admin accounts created in the admin console are saved in the config database and carry over to any later stack that uses the same database, which also switches authentication on."
  type        = string
  default     = ""
  sensitive   = true
}

# --- Single sign-on (optional) --------------------------------------------------------------
# Leave oidc_issuer blank to keep the default login. One registration with the identity provider serves
# both the admin console and the Ask app; register the redirect URIs /auth/oidc/callback and
# /app/oidc/callback.

variable "oidc_issuer" {
  description = "OpenID Connect issuer URL, e.g. https://your-org.okta.com/oauth2/default or https://dev-abc.us.auth0.com. https:// is added if you leave it off. Setting it turns on single sign-on."
  type        = string
  default     = ""
}

variable "oidc_client_id" {
  description = "Client ID of the OIDC web application registered with the provider. Required when oidc_issuer is set."
  type        = string
  default     = ""
}

variable "oidc_client_secret" {
  description = "Client secret of that application. Required when oidc_issuer is set."
  type        = string
  default     = ""
  sensitive   = true
}

variable "oidc_scopes" {
  description = "Scopes to request. Add \"groups\" only if the provider is set up to return a groups claim."
  type        = string
  default     = "openid profile email"
}

variable "oidc_admin_users" {
  description = "Comma-separated email addresses that get the admin role when they sign in with single sign-on. Everyone else who signs in is read-only in the admin console."
  type        = string
  default     = ""
}

variable "oidc_admin_groups" {
  description = "Comma-separated values of the groups claim that grant the admin role. Optional."
  type        = string
  default     = ""
}

# --- Tuning and diagnostics ------------------------------------------------------------------

variable "omnigate_memory_limit_gb" {
  description = "Memory limit (GB) for each OmniGate pod. The JVM heap is omnigate_max_ram_percentage of this. 3 is enough for the demo and the small TPC-H sizes; a join over TPC-H scale factor 1 (1.5M orders hashed in memory) ran out of heap at 3GB (about 2GB of heap), so use 6 or more for it. Keep it within what a node can hold alongside the other pods."
  type        = number
  default     = 3
}

variable "omnigate_max_ram_percentage" {
  description = "JVM heap as a percentage of each pod's memory limit. The JVM default of 25 leaves a 3Gi pod with a 768MB heap, which the S3/Parquet connector exhausts even on a 600,000-row table; 65 gives about 2GB."
  type        = number
  default     = 65
}

variable "omnigate_parallel_join_min_rows" {
  description = "Row count below which the parallel hash join is skipped. Blank keeps the app default (10000). Lower it (for example to 1) only to exercise the parallel join on small demo tables."
  type        = string
  default     = ""
}

variable "omnigate_remote_join_enabled" {
  description = "On a clustered deployment (more than one replica), let the parallel hash join ship work to the other replicas. Turn it off to compare against a run where one replica does everything."
  type        = bool
  default     = true
}

variable "omnigate_debug_federation" {
  description = "Turn on debug logging for the federation package. The planner logs why it did or did not use the parallel join engine only at debug level."
  type        = bool
  default     = false
}

# --- Optional demo dataset ------------------------------------------------------------------

variable "enable_tpch_demo" {
  description = "Also load a TPC-H demo dataset: LINEITEM as Parquet in an in-cluster S3-compatible store, the other seven tables in a `tpch` database in the existing Postgres. Adds two data backends on top of the three supply-chain ones, so it needs a commercial-edition image (the free edition caps at three). The loader runs on first deploy and takes several minutes at scale factor 1; the OmniGate pods wait for it."
  type        = bool
  default     = false
}

variable "tpch_lineitem_store" {
  description = "Where the TPC-H LINEITEM table lives: \"postgres\" (a second database, so the big join is database to database, which is the only shape the parallel hash join can plan) or \"s3\" (Parquet in an in-cluster object store; joins that include it never use the parallel engine, and the connector reads whole files onto the heap)."
  type        = string
  default     = "postgres"

  validation {
    condition     = contains(["postgres", "s3"], var.tpch_lineitem_store)
    error_message = "tpch_lineitem_store must be \"postgres\" or \"s3\"."
  }
}

variable "tpch_scale_factor" {
  description = "TPC-H scale factor when enable_tpch_demo is on. 1 is about 1GB of source data (6M lineitem rows, 1.5M orders); 0.1 is a ten-times smaller smoke-test size."
  type        = number
  default     = 1
}

# --- Image ----------------------------------------------------------------------------------

variable "image_repository" {
  description = "Fully-qualified OCIR path for the omnigate image. Defaults to the publisher's own pre-built image -- Marketplace deployers should not need to build anything themselves."
  type        = string
  default     = "ocir.us-phoenix-1.oci.oraclecloud.com/ax8tpjdxhykk/omnigate"
}

variable "image_tag" {
  description = "Image tag to deploy. Pinned to a specific free-edition release rather than \"latest\" -- confirmed live that \"latest\" had silently stopped tracking new app releases (frozen at v0.6.0's content for two releases), so a moving-target default wasn't actually keeping deployers current anyway, just non-reproducible. Bump this deliberately when a newer free-edition image is built and pushed to OCIR."
  type        = string
  default     = "v0.10.4"
}

variable "image_pull_username" {
  description = "Only needed when image_repository points at a private repository (e.g. a commercial-edition build kept out of the free image's public repo) -- OCIR's own \"<tenancy-namespace>/<oci-username>\" format. Leave blank for the default public free-image path, which needs no credentials at all."
  type        = string
  default     = ""
}

variable "image_pull_auth_token" {
  description = "Password half of image_pull_username: an OCI Auth Token (Identity -> Users -> your user -> Auth Tokens -> Generate Token), NOT your console password or API signing key. Required alongside image_pull_username for a private image_repository; ignored for the default public path."
  type        = string
  sensitive   = true
  default     = ""
}

# --- Compute sizing (Always Free: VM.Standard.A1.Flex, Ampere) ------------------------------

variable "node_pool_size" {
  description = "Number of worker nodes -- a floor, not the final word: automatically raised to at least omnigate_replica_count if you set this lower (see oke.tf's local.effective_node_pool_size), since one OmniGate replica per node is what this stack's default node sizing actually fits. Confirmed live: leaving this below the replica count schedules the first couple of pods fine, then the rest sit Pending forever with no node to place them on."
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
