output "cluster_id" {
  value = oci_containerengine_cluster.this.id
}

output "kubeconfig_command" {
  description = "Run this locally to fetch a kubeconfig for kubectl access."
  value       = "oci ce cluster create-kubeconfig --cluster-id ${oci_containerengine_cluster.this.id} --file $HOME/.kube/config --region ${var.region} --token-version 2.0.0"
}

output "ask_app_url" {
  description = "Populated by polling the LoadBalancer for up to 3 minutes after Helm installs -- OCI's own LB IP assignment is asynchronous, so on a slow provision this can still come back empty. If so, run `kubectl get svc omnigate-omnigate-http -n default` (see README) once the IP has had a bit longer to appear."
  value = (
    data.external.ask_app_lb_ip.result.ip != ""
    ? "http://${data.external.ask_app_lb_ip.result.ip}:8080/"
    : "<pending-lb-ip> -- not yet assigned after 3 minutes of polling; see README for the kubectl fallback command"
  )
}
