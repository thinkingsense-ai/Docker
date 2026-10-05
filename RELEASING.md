# Releasing

How app versions, the free and commercial images, and the cloud stacks relate, and how a new
version reaches deployers. Status markers: **[today]** is how it works now, **[proposed]** is not
built yet.

## Three things with three lifecycles

| Thing | Where | Version looks like | Changes |
|---|---|---|---|
| The app (OmniGate) | private `Server` repo | `v0.10.3` | fast |
| Container images | OCIR: `omnigate` (free, public), `omnigate-commercial` (private) | the app's tag | when the app releases |
| Cloud stacks (AWS/OCI/GCP/Azure) | this repo, `resource-manager/*` | `oke-stack-v1.1.5`, `eks-stack-v1.0.7`, ... | when infra changes |

A stack never contains the app. It pins an image tag and deploys it, so an app release does not
require a stack release, and a stack fix does not require an app release.

## One source line, two editions

The free and commercial images are the same commit. Edition is a marker baked into the image
(`/opt/omnigate/EDITION`), which wins over the `OMNIGATE_EDITION` env var. Commercial-only
behavior, such as Ignite clustering, is gated at runtime on that marker.

- **Do not keep a long-lived commercial branch of the app.** A commercial-only code fork becomes a
  merge problem at the app's release pace.
- **Do not ship one-off builds.** `v0.8.0-oracle-fix` was built from an unmerged Server PR and
  exists only in the private repo. Merge such fixes and release them as a normal patch (v0.10.4).

## Branches **[proposed]**

- `main` is the current line (0.10.x) until 0.11 work begins.
- When 0.11 work starts, cut `release/0.10` from the last 0.10 tag and let `main` move on.
- Commercial only consumes patch releases from the release branch (v0.10.4, v0.10.5, ...).
- Fixes land on `main` first, then are cherry-picked to `release/0.10`.

## Promotion: candidate, tested, released **[proposed]**

An image reaches deployers by being promoted, not by being the newest build.

1. Tag the app (`vX.Y.Z`, or `vX.Y.Z-rc.N` for a candidate). CI builds both editions.
2. Push to a **staging** tag in OCIR. Never push a candidate to the public repo or to `latest`.
3. Run the commercial suite against the candidate (below).
4. On a pass, retag to `vX.Y.Z` in `omnigate` (free) and `omnigate-commercial` (private).
5. Bump the stack pins (below). Commercial deploys should pin by image digest.

### Commercial suite

Clean-room deploy from the stack zip on a real tenancy, then:

- Pods reach Ready and log `cluster joined, current size=N` on every pod.
- Scale 2 to 3 (and 3 to 4) through Resource Manager. No `ORA-` errors, and no failed probes
  beyond a single blip during the rolling restart.
- Config store on Oracle (26ai) and on Postgres.
- The ADB ACL step adds the new node IPs before the new pod starts, and removes them on destroy.
- Ask-app login works with the password set at deploy time.
- Destroy leaves no orphaned volumes or load balancers.

## Bumping the pinned version

**[today]** The image tag is set in several places that must agree: `variables.tf` default,
`schema.yaml` default, the stack README, and `helm/omnigate/values.yaml`. A bulk bump once missed
`schema.yaml`, leaving the Console wizard on v0.8.0 while Terraform defaulted to v0.10.0, and the
Terraform default pointed at a tag that did not exist in the default registry.

When bumping:

1. Confirm the tag exists in the registry the stack pulls from, free and commercial.
2. Change every reference in one PR. Search the whole repo for the old tag, not just one stack.
3. Cut the stack release (below).

**[proposed]** A CI check that fails the PR when those references disagree.

### Minor and patch (v0.10.3 to v0.10.4)

Promote as above, then bump the pins. Rolling upgrade in place is expected to work, but verify it
on the commercial suite for each release.

### Major or minor with schema changes (v0.10.x to v0.11)

1. `v0.11.0-rc.1` to a staging tag; run the commercial suite.
2. Run an **in-place upgrade test** from the latest 0.10.x: config-store migrations (Oracle and
   Postgres), and Ask-app behavior after upgrade.
3. **Test a mixed-version Ignite cluster.** During a rolling update, old and new pods share a
   cluster for a while. This is untested. If nodes of different versions cannot coexist, a major
   bump must be blue/green: stand up a new cluster against the same config database and cut the
   load balancer over, not roll the pods.
4. Promote, then bump the pins in one PR.
5. Keep `release/0.10` patchable for an agreed window after 0.11 ships.

## Cutting a stack release

Tag `eks-stack-vX.Y.Z`, `oke-stack-vX.Y.Z`, `gke-stack-vX.Y.Z` or `aks-stack-vX.Y.Z`, then update the
docs site (`deploy-*.html`): the Launch Stack or Deploy buttons, the zip links and the CLI
snippets. Each stack's README has its own "Publishing a release" section.

**Always pass `--latest=false` for stack tags.** App releases and stack releases share one GitHub
Releases list, and `password-hash.tf` resolves the app jar through `/releases/latest`. A stack
release that becomes "latest" breaks every fresh deploy on all four clouds. Fix with
`gh release edit <app-tag> --repo thinkingsense-ai/Docker --latest`.

**[proposed]** The hash step should download the jar for the image's base version (strip any
`-suffix`, so `v0.8.0-oracle-fix` uses `v0.8.0`) and fall back to latest only if no such release
exists. Today it falls back to latest for any non-release tag, so the pods can run 0.8 while the
password is hashed by 0.10.3.
