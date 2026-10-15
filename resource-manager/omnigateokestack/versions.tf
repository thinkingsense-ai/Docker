terraform {
  required_version = ">= 1.5.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.0.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
    helm = {
      source = "hashicorp/helm"
      # Excludes 2.17.x: that release's plugin process crashed intermittently ("Unrecognized remote plugin message",
      # thinkingsense-ai/Docker#7). Raise the ceiling only after a newer release has been run clean.
      version = ">= 2.12.0, < 2.17.0"
    }
    external = {
      source  = "hashicorp/external"
      version = "~> 2.3"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
}

provider "oci" {
  region = var.region
}
