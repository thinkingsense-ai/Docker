import json
import os
import subprocess
import time
import urllib.request
import base64
import boto3
import botocore.session
from botocore.signers import RequestSigner

TASK_ROOT = os.environ.get("LAMBDA_TASK_ROOT", "/var/task")
CHART_PATH = os.path.join(TASK_ROOT, "omnigate-chart")
STORAGECLASS_PATH = os.path.join(TASK_ROOT, "storageclass.yaml")
KUBECONFIG_PATH = "/tmp/kubeconfig"


def send_response(event, context, status, reason="", data=None, physical_resource_id=None):
    response_body = json.dumps({
        "Status": status,
        "Reason": reason or f"See CloudWatch Logs: {context.log_stream_name}",
        "PhysicalResourceId": physical_resource_id or event.get("PhysicalResourceId") or context.log_stream_name,
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "NoEcho": False,
        "Data": data or {},
    }).encode("utf-8")
    req = urllib.request.Request(
        event["ResponseURL"], data=response_body, method="PUT",
        headers={"Content-Type": "", "Content-Length": str(len(response_body))},
    )
    urllib.request.urlopen(req)


def get_bearer_token(cluster_name, region):
    # Same STS-presigned-URL technique `aws eks get-token` / kubectl's aws-iam-authenticator
    # exec plugin uses -- no extra CLI binary needed, just boto3 (already in the Lambda runtime).
    session = botocore.session.get_session()
    client = session.create_client("sts", region_name=region)
    service_id = client.meta.service_model.service_id
    signer = RequestSigner(
        service_id, region, "sts", "v4",
        session.get_credentials(), session.get_component("event_emitter"),
    )
    params = {
        "method": "GET",
        "url": f"https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15",
        "body": {},
        "headers": {"x-k8s-aws-id": cluster_name},
        "context": {},
    }
    signed_url = signer.generate_presigned_url(params, region_name=region, expires_in=900, operation_name="")
    token = "k8s-aws-v1." + base64.urlsafe_b64encode(signed_url.encode("utf-8")).decode("utf-8").rstrip("=")
    return token


def write_kubeconfig(cluster_name, region, path):
    eks = boto3.client("eks", region_name=region)
    cluster = eks.describe_cluster(name=cluster_name)["cluster"]
    endpoint = cluster["endpoint"]
    ca = cluster["certificateAuthority"]["data"]
    token = get_bearer_token(cluster_name, region)
    kubeconfig = f"""apiVersion: v1
kind: Config
clusters:
- cluster:
    server: {endpoint}
    certificate-authority-data: {ca}
  name: cluster
contexts:
- context:
    cluster: cluster
    user: aws
  name: ctx
current-context: ctx
users:
- name: aws
  user:
    token: {token}
"""
    with open(path, "w") as f:
        f.write(kubeconfig)


def run_cmd(binary, args, timeout=540):
    env = dict(os.environ)
    env["KUBECONFIG"] = KUBECONFIG_PATH
    # Lambda's $HOME is read-only -- `helm repo add` (and Helm's config/cache dirs generally)
    # need a writable HOME. Confirmed live: "Error: mkdir .config: read-only file system".
    env["HOME"] = "/tmp"
    env["XDG_CONFIG_HOME"] = "/tmp/.config"
    env["XDG_CACHE_HOME"] = "/tmp/.cache"
    env["XDG_DATA_HOME"] = "/tmp/.local/share"
    result = subprocess.run([binary] + args, capture_output=True, text=True, env=env, timeout=timeout)
    print(f"{binary} stdout:", result.stdout)
    print(f"{binary} stderr:", result.stderr)
    if result.returncode != 0:
        safe_args = " ".join(a for a in args if "password" not in a.lower())
        raise RuntimeError(f"{binary} command failed: {safe_args}\n{result.stderr}")
    return result.stdout


def run_helm(args):
    return run_cmd("helm", args)


def resolve_jar_url(image_tag):
    # image_tag is the OCIR *docker* tag (default "latest"), which is not itself a GitHub
    # release tag -- there is no release literally named "latest". When it's an actual version
    # (e.g. "v0.6.0") that matches a real release, use it directly; otherwise resolve the
    # GitHub API's own "latest release" so the jar always matches whatever OCIR's :latest
    # currently points at.
    if image_tag and image_tag != "latest":
        return f"https://github.com/thinkingsense-ai/Docker/releases/download/{image_tag}/omnigate.jar"
    api_url = "https://api.github.com/repos/thinkingsense-ai/Docker/releases/latest"
    with urllib.request.urlopen(api_url, timeout=15) as resp:
        release = json.loads(resp.read())
    for asset in release.get("assets", []):
        if asset["name"] == "omnigate.jar":
            return asset["browser_download_url"]
    raise RuntimeError("omnigate.jar asset not found on latest GitHub release")


def compute_password_hash(password, image_tag):
    # Same technique used to fix the OCI stack's own password UX (Docker#15/#16): download the
    # exact release jar being deployed and run its own bundled PasswordHash utility, so the hash
    # format always matches whatever's actually deployed rather than a separately-maintained
    # reimplementation of the hashing algorithm.
    jar_path = "/tmp/omnigate-hash-tool.jar"
    subprocess.run(
        ["curl", "-fsSL", "-o", jar_path, resolve_jar_url(image_tag)],
        check=True, timeout=60,
    )
    result = subprocess.run(
        ["java", "-cp", jar_path, "com.omnigate.http.auth.PasswordHash", password],
        capture_output=True, text=True, timeout=30,
    )
    os.remove(jar_path)
    if result.returncode != 0:
        raise RuntimeError(f"PasswordHash failed: {result.stderr}")
    return result.stdout.strip()


def ensure_lbc(cluster_name, region, vpc_id, role_arn):
    # Without this, Kubernetes Services of type LoadBalancer fall back to AWS's deprecated
    # in-tree provisioner, which only creates Classic ELBs. Same lesson as OCI's own security
    # list fix: a Classic LB buffers Server-Sent Events, breaking the Ask app's live streaming
    # trace. Installed idempotently on every deploy since it's cheap and this Lambda has no
    # persistent state to know if a previous deploy already did it.
    run_cmd("helm", ["repo", "add", "eks-charts", "https://aws.github.io/eks-charts"], timeout=60)
    run_cmd("helm", ["repo", "update"], timeout=60)
    run_cmd("helm", [
        "upgrade", "--install", "aws-load-balancer-controller", "eks-charts/aws-load-balancer-controller",
        "--namespace", "kube-system",
        "--set", f"clusterName={cluster_name}",
        "--set", f"region={region}",
        "--set", f"vpcId={vpc_id}",
        "--set", "serviceAccount.create=true",
        "--set", "serviceAccount.name=aws-load-balancer-controller",
        "--set", f"serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn={role_arn}",
        "--wait", "--timeout", "5m",
    ])


def get_lb_hostname(namespace, service_name, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        hostname = run_cmd(
            "kubectl",
            ["get", "svc", service_name, "-n", namespace,
             "-o", "jsonpath={.status.loadBalancer.ingress[0].hostname}"],
            timeout=30,
        ).strip()
        if hostname:
            return hostname
        time.sleep(10)
    return ""


def ensure_storageclass():
    # EKS has no built-in CSI driver (unlike OKE) -- the EBS CSI Addon provisions the driver
    # itself but not a StorageClass to use it, so Postgres's PVC would sit Pending forever
    # without this.
    run_cmd("kubectl", ["apply", "-f", STORAGECLASS_PATH], timeout=60)


def _find_cluster_load_balancers(elbv2, cluster_name):
    # The Load Balancer Controller tags every LB it creates with elbv2.k8s.aws/cluster=<name>
    # (confirmed live against an actual created NLB) -- NOT the kubernetes.io/cluster/<name>=owned
    # convention that EC2 subnets/security groups outside the LBC's own resources use.
    lbs = elbv2.describe_load_balancers().get("LoadBalancers", [])
    if not lbs:
        return []
    arns = [lb["LoadBalancerArn"] for lb in lbs]
    owned = []
    for td in elbv2.describe_tags(ResourceArns=arns)["TagDescriptions"]:
        tags = {t["Key"]: t["Value"] for t in td["Tags"]}
        if tags.get("elbv2.k8s.aws/cluster") == cluster_name:
            owned.append(td["ResourceArn"])
    return owned


def wait_for_lb_cleanup(cluster_name, region, timeout=240):
    # `helm uninstall --wait` waits for the Service object's finalizer to clear, which is
    # supposed to mean the Load Balancer Controller already deleted the underlying NLB -- but
    # confirmed live: even with the controller alive and healthy the whole time, an NLB can be
    # left fully orphaned (never even started deleting) after a normal `helm uninstall`. Rather
    # than trust the finalizer, poll for the LB to actually disappear, and if it's still there
    # after a reasonable wait, delete it (and its security groups) directly -- otherwise it
    # permanently blocks this same stack's later VPC/IGW deletion.
    elbv2 = boto3.client("elbv2", region_name=region)
    deadline = time.time() + timeout
    owned = []
    while time.time() < deadline:
        owned = _find_cluster_load_balancers(elbv2, cluster_name)
        if not owned:
            return
        time.sleep(10)

    print(f"WARNING: {len(owned)} load balancer(s) for cluster {cluster_name} still present "
          f"after {timeout}s -- deleting directly so VPC teardown isn't blocked: {owned}")
    sg_ids = set()
    for arn in owned:
        try:
            lb = elbv2.describe_load_balancers(LoadBalancerArns=[arn])["LoadBalancers"][0]
            sg_ids.update(lb.get("SecurityGroups", []))
        except Exception as e:
            print(f"describe_load_balancers failed for {arn}: {e}")
        try:
            elbv2.delete_load_balancer(LoadBalancerArn=arn)
        except Exception as e:
            print(f"delete_load_balancer failed for {arn}: {e}")

    if sg_ids:
        # ENIs take a little while to detach after delete_load_balancer returns; security group
        # deletion fails with DependencyViolation until they do.
        ec2 = boto3.client("ec2", region_name=region)
        sg_deadline = time.time() + 60
        remaining = set(sg_ids)
        while remaining and time.time() < sg_deadline:
            for sg_id in list(remaining):
                try:
                    ec2.delete_security_group(GroupId=sg_id)
                    remaining.discard(sg_id)
                except Exception:
                    pass
            if remaining:
                time.sleep(10)
        for sg_id in remaining:
            print(f"WARNING: could not delete security group {sg_id} (still has dependencies)")


def lambda_handler(event, context):
    # Confirmed live: this redacted ResourceProperties but NOT OldResourceProperties (present on
    # Update events), which meant the *previous* AppPassword value was logged to CloudWatch in
    # plaintext on every password change. Both must be scrubbed the same way.
    REDACT = {"AppPassword", "LlmApiKey", "HelmSetSensitiveValues"}
    safe_event = {
        k: v for k, v in event.items() if k not in ("ResourceProperties", "OldResourceProperties")
    }
    for key in ("ResourceProperties", "OldResourceProperties"):
        if key in event:
            safe_event[key] = {k: v for k, v in event[key].items() if k not in REDACT}
    print("event:", json.dumps(safe_event))

    props = event.get("ResourceProperties", {})
    request_type = event["RequestType"]
    cluster_name = props["ClusterName"]
    region = props.get("Region", os.environ.get("AWS_REGION"))
    release_name = props.get("ReleaseName", "omnigate")
    namespace = props.get("Namespace", "default")
    physical_id = f"{cluster_name}/{namespace}/{release_name}"

    try:
        write_kubeconfig(cluster_name, region, KUBECONFIG_PATH)

        if request_type in ("Create", "Update"):
            ensure_storageclass()
            ensure_lbc(cluster_name, region, props["VpcId"], props["LbcRoleArn"])
            image_tag = props.get("HelmSetValues", {}).get("image.tag", "latest")
            app_username = props.get("AppUsername", "demo")
            app_password = props["AppPassword"]
            password_hash = compute_password_hash(app_password, image_tag)

            set_values = dict(props.get("HelmSetValues", {}))
            set_values.setdefault("storageClassName", "gp3")
            set_sensitive_values = {"omnigate.appUsers": f"{app_username}:{password_hash}::"}
            if props.get("LlmApiKey"):
                set_sensitive_values["omnigate.llmApiKey"] = props["LlmApiKey"]
            args = [
                "upgrade", "--install", release_name, CHART_PATH,
                "--namespace", namespace, "--create-namespace",
                "--wait", "--timeout", "8m",
            ]
            for k, v in set_values.items():
                args += ["--set", f"{k}={v}"]
            for k, v in set_sensitive_values.items():
                args += ["--set", f"{k}={v}"]
            run_helm(args)
            lb_host = get_lb_hostname(namespace, f"{release_name}-omnigate-http")
            ask_app_url = f"http://{lb_host}:8080/" if lb_host else ""
            send_response(event, context, "SUCCESS", physical_resource_id=physical_id, data={"AskAppUrl": ask_app_url})

        elif request_type == "Delete":
            try:
                run_helm(["uninstall", release_name, "--namespace", namespace, "--wait", "--timeout", "5m"])
            except Exception as e:
                print("uninstall error (continuing so stack deletion isn't blocked):", e)
            try:
                wait_for_lb_cleanup(cluster_name, region)
            except Exception as e:
                print("lb cleanup check error (continuing so stack deletion isn't blocked):", e)
            send_response(event, context, "SUCCESS", physical_resource_id=event.get("PhysicalResourceId", physical_id))

    except Exception as e:
        print("ERROR:", repr(e))
        send_response(event, context, "FAILED", reason=str(e)[:1000], physical_resource_id=physical_id)
