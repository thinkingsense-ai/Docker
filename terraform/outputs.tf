output "cluster_id" {
  value = oci_containerengine_cluster.this.id
}

output "kubeconfig_command" {
  description = "Run this locally to fetch a kubeconfig for kubectl access."
  value       = "oci ce cluster create-kubeconfig --cluster-id ${oci_containerengine_cluster.this.id} --file $HOME/.kube/config --region ${var.region} --token-version 2.0.0"
}

output "ask_app_url" {
  description = "Populated once the LoadBalancer gets a public IP -- may take a few minutes after apply finishes; check `kubectl get svc` if empty. Serves both the Ask app (/) and the admin console (/admin) on the same port -- see the OMNIGATE_ASK_PORT note in helm/omnigate/templates/omnigate.yaml for why these aren't split."
  value       = "http://<pending-lb-ip>:8080/  (run `kubectl get svc omnigate-omnigate-http` to get the real IP once provisioned)"
}
