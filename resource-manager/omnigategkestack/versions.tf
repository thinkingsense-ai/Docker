terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
    external = {
      source  = "hashicorp/external"
      version = "~> 2.3"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}
