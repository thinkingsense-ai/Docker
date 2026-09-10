output "cluster_id" {
  value = oci_containerengine_cluster.this.id
}

output "kubeconfig_command" {
  description = "Run this locally to fetch a kubeconfig for kubectl access."
  value       = "oci ce cluster create-kubeconfig --cluster-id ${oci_containerengine_cluster.this.id} --file $HOME/.kube/config --region ${var.region} --token-version 2.0.0"
}

output "ask_app_url" {
  description = "Populated once the LoadBalancer gets a public IP -- may take a few minutes after apply finishes; check `kubectl get svc` if empty. The admin console is deliberately NOT exposed here -- it's ClusterIP-only; reach it with `kubectl port-forward svc/omnigate-omnigate-admin 8080:8080`."
  value       = "http://<pending-lb-ip>:8081/  (run `kubectl get svc omnigate-omnigate-ask` to get the real IP once provisioned)"
}
