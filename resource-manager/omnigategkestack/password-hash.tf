# Computes OMNIGATE_APP_USERS / OMNIGATE_AUTH_USERS during apply, so deployers never hand-assemble a
# "username:saltB64:hashB64::" string.
#
# The hash is STABLE across applies (issue #59). It used to run the release jar's PasswordHash on
# every plan, and that utility draws a fresh random salt each run -- so the Secret's hashes changed on
# every apply, `checksum/secret` on the pod template followed them, and Kubernetes rolled the pod even
# when the only change was unrelated (a licence, a debug flag, scale). Now the salts are `random_id`
# resources, which live in Terraform state and never change, and the PBKDF2 is computed here with
# python3's hashlib from (password, salt). Same password + same salt = the same hash, so the Secret
# only changes when a password changes. It also means no jar download, no JRE and no network egress.
#
# FORMAT CONTRACT: this must reproduce com.omnigate.http.auth.PasswordHash exactly --
# PBKDF2-HMAC-SHA256, 210000 iterations, 32-byte key, 16-byte salt, "saltB64:hashB64". The Server
# repo pins that contract in PasswordHashTest.matchesTheTerraformStacksPythonImplementation; if
# the iteration count ever changes there, change `iterations` below in the same release.
#
# Still a `data "external"` source, not a null_resource + local_file: a file written by an earlier
# apply job does not exist when a later destroy job runs, and a data source is read in every
# operation. The program is deterministic now, so re-running it on every plan changes nothing.
# Passwords and salts arrive as JSON on stdin and are parsed with python3, so quotes, backslashes
# or unicode in a real password cannot break the parse.
resource "random_id" "app_password_salt" {
  byte_length = 16
}

resource "random_id" "admin_password_salt" {
  byte_length = 16
}

data "external" "app_password_hash" {
  program = ["python3", "-c", <<-EOT
import base64, hashlib, json, sys
q = json.load(sys.stdin)
iterations = 210000  # = PasswordHash.ITERATIONS in the Server repo


def entry(password, salt_b64):
    salt = base64.b64decode(salt_b64)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, 32)
    return salt_b64 + ":" + base64.b64encode(key).decode("ascii")


print(json.dumps({"hash": entry(q["password"], q["salt"]), "admin_hash": entry(q["admin_password"], q["admin_salt"])}))
  EOT
  ]

  query = {
    password = var.omnigate_app_password
    # Blank means "use the Ask-app password for the admin login too" (see omnigate_admin_password).
    admin_password = var.omnigate_admin_password != "" ? var.omnigate_admin_password : var.omnigate_app_password
    salt           = random_id.app_password_salt.b64_std
    admin_salt     = random_id.admin_password_salt.b64_std
  }
}

locals {
  # "username:saltB64:hashB64::" -- the exact OMNIGATE_APP_USERS format the app expects.
  omnigate_app_users_computed = "${var.omnigate_app_username}:${data.external.app_password_hash.result.hash}::"

  # Local admin login for the admin console, admin API and /mcp: "user:saltB64:hashB64:admin".
  omnigate_auth_users_computed = "${var.omnigate_admin_username}:${data.external.app_password_hash.result.admin_hash}:admin"
}
