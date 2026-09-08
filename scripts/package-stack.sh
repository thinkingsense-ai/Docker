#!/usr/bin/env bash
# Packages terraform/ into the zip Resource Manager expects: schema.yaml and *.tf at the ZIP
# ROOT (not nested in a subdirectory). The Helm chart lives at terraform/helm/omnigate, so it's
# already correctly nested for both local `terraform apply` (relative path ./helm/omnigate from
# path.module) and an ORM-uploaded zip (same relative layout, since the zip root IS terraform/'s
# contents) -- no separate copy/merge step needed.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="omnigate-oke-stack.zip"
rm -f "$OUT"

(cd terraform && zip -r "../$OUT" . -x '.terraform/*')

echo "Wrote $OUT -- upload this in OCI Console > Resource Manager > Stacks > Create Stack > My Configuration."
