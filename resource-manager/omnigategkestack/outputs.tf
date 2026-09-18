output "cluster_name" {
  value = google_container_cluster.this.name
}

output "kubeconfig_command" {
  description = "Run this locally to fetch a kubeconfig for kubectl access."
  value       = "gcloud container clusters get-credentials ${google_container_cluster.this.name} --zone ${google_container_cluster.this.location} --project ${var.gcp_project_id}"
}

output "ask_app_url" {
  description = "Populated once the LoadBalancer gets a public IP -- may take a few minutes after apply finishes; check `kubectl get svc` if empty."
  value       = "http://<pending-lb-ip>:8080/  (run `kubectl get svc omnigate-omnigate-http` to get the real IP once provisioned)"
}
