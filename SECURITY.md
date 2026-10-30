# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's private reporting instead:
**Security tab > Report a vulnerability** on this repository (https://github.com/thinkingsense-ai/Docker/security/advisories/new).
A problem in the server itself can be reported the same way at https://github.com/thinkingsense-ai/Server/security/advisories/new.

We acknowledge a report within three working days and tell you what we plan to do about it within ten.

## Scope

The Compose files, Helm charts, Terraform and ARM/Bicep stacks, and the images built from the Dockerfiles here. Known gaps and their status are listed at
https://thinkingsense-ai.github.io/security.html.

## How we check

`.github/workflows/image-scan.yml` scans the published images for known vulnerabilities each week and on every change to a Dockerfile, and writes a software
bill of materials for each image.
