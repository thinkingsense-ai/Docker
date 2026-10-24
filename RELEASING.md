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

## Automated image build **[today]**

Publishing an app release (`vX.Y.Z`) runs `.github/workflows/build-images.yml`, which replaces building and pushing the images by hand:

1. Checks the release has `omnigate.jar` and `web-dist.tar.gz` (the Dockerfile downloads them by tag).
2. Builds the **free** and **commercial** images for arm64 on a native arm64 runner, and checks each image's edition marker.
3. Pushes `omnigate:<tag>` (free, public) and `omnigate-commercial:<tag>` (private) to OCIR, and `omnigate:<tag>` to the Google Artifact
   Registry (GKE and AKS pull from there). A release candidate (`vX.Y.Z-rc.N`) goes to OCIR only.
4. Opens a PR "Bump pins to <tag>" with every stack pin moved by `scripts/version-pins.py`. **Merging it stays a person's decision**: do the
   clean-room checks first, then cut the stack releases whose default image changed.

Stack releases (`oke-stack-v*` and the others) share the Releases list but are ignored by the workflow.

**Dry run, no secrets needed:** Actions > Build images > Run workflow, tag `v0.10.6`, "push" off. It builds both images and checks the markers.

**One-time setup** (Settings > Secrets and variables > Actions):

| Secret | What |
|---|---|
| `OCIR_USERNAME` | `<tenancy namespace>/<oci user>` of a user allowed to push to the `omnigate` and `omnigate-commercial` repositories |
| `OCIR_AUTH_TOKEN` | that user's OCI Auth Token |
| `GAR_SERVICE_ACCOUNT_KEY` | JSON key of a Google service account whose only role is Artifact Registry Writer on the `omnigate` repository |

And Settings > Actions > General > Workflow permissions: tick "Allow GitHub Actions to create and approve pull requests" so step 4 can open the PR.
Prefer short-lived credentials later (OIDC federation to Google and Oracle) over long-lived keys.

## The ghcr images **[today]**

Besides the OCIR and Artifact Registry images above, each app release is also published as `ghcr.io/thinkingsense-ai/server`
(the images the Server README and `docker-compose.yml` name). They are built from the Server repo's own Dockerfiles, on an arm64
machine, and pushed by hand:

```bash
cd Server                      # at the release commit, with docs/releases/<version>.md written and AppVersion bumped
docker build -f Dockerfile.commercial -t ghcr.io/thinkingsense-ai/server:0.10.9 -t ghcr.io/thinkingsense-ai/server:0.10 .
docker build -f Dockerfile.free       -t ghcr.io/thinkingsense-ai/server:0.10.9-free .
docker run --rm --entrypoint cat ghcr.io/thinkingsense-ai/server:0.10.9 /opt/omnigate/EDITION        # commercial
docker run --rm --entrypoint cat ghcr.io/thinkingsense-ai/server:0.10.9-free /opt/omnigate/EDITION   # free
docker push ghcr.io/thinkingsense-ai/server:0.10.9 && docker push ghcr.io/thinkingsense-ai/server:0.10 \
  && docker push ghcr.io/thinkingsense-ai/server:0.10.9-free
```

Order of a release as done for v0.10.9: full `mvn test` (only environment errors allowed: the container-dependent connector tests),
bump `AppVersion`, write the release notes, push the Server `main`; build the images and push them to ghcr; create the Server
release (notes only) and the Docker release with `omnigate.jar` and `web-dist.tar.gz` (`tar -czf web-dist.tar.gz -C web/dist .`);
the **Build images** workflow then pushes OCIR and Artifact Registry and opens the "Bump pins" PR; check `version-pins.py check`
and merge it. The stack releases (below) are cut separately, after the clean-room checks.

## Promotion: candidate, tested, released **[proposed]**

An image reaches deployers by being promoted, not by being the newest build.

1. Tag the app (`vX.Y.Z`, or `vX.Y.Z-rc.N` for a candidate). CI builds both editions.
2. Push to a **staging** tag in OCIR. Never push a candidate to the public repo or to `latest`.
3. Run the commercial suite against the candidate (below).
4. On a pass, retag to `vX.Y.Z` in `omnigate` (free) and `omnigate-commercial` (private).
5. Bump the stack pins (below). Commercial deploys should pin by image digest.

### Commercial suite

The steps below are automated where possible by `scripts/commercial-harness/` (see its README):
`verify-correctness.py` for answers, `oidc-test.sh` for cross-replica sign-in.

Clean-room deploy from the stack zip on a real tenancy, then:

- Pods reach Ready and log `cluster joined, current size=N` on every pod.
- Scale 2 to 3 (and 3 to 4) through Resource Manager. No `ORA-` errors, and no failed probes
  beyond a single blip during the rolling restart.
- Config store on Oracle (26ai) and on Postgres.
- The ADB ACL step adds the new node IPs before the new pod starts, and removes them on destroy.
- Ask-app login works with the password set at deploy time.
- Destroy leaves no orphaned volumes or load balancers.

## Bumping the pinned version

**[today]** The image tag is pinned in several places that must agree. `scripts/version-pins.py`
knows all of them and groups them by the registry each one pulls from:

```bash
scripts/version-pins.py check [--verify-ocir]   # fails if the core pins disagree
scripts/version-pins.py bump v0.10.4            # bumps the core group
scripts/version-pins.py bump v0.10.4 --group gke --group aks   # only once their registry has it
```

`core` is the Dockerfiles, the compose file and the OKE stack (variables.tf and schema.yaml);
`check --verify-ocir` also confirms the tag exists in both OCIR repos. `gke` and `aks` are
separate groups because each cloud pulls from its own registry, and a tag that exists in OCIR
may not exist there. A bulk bump once missed `schema.yaml` and pointed a Terraform default at a
tag that did not exist in the default registry; that is what this prevents.

To bump: build and promote the image (above), run `bump`, run `check --verify-ocir`, update
prose mentions in the READMEs, open one PR, then cut the stack release (below).

**[proposed]** Run `check` in CI so a PR that desyncs the core pins cannot merge.

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

**Order, per release** (a stack release is needed whenever a stack's chart, template or default image changed; an app release alone
moves nothing until the pins are bumped and the stacks are re-released):

1. Merge the pin PR ("Bump pins to vX.Y.Z", opened by the Build images workflow) after the clean-room checks.
2. **Move the self-pins** to the stack release about to be cut, in one PR per stack, and merge it **before tagging**:
   `scripts/version-pins.py bump-self eks vX.Y.Z` (the EKS template's `Release.Current.Tag`, which is what CodeBuild checks out to build the
   deployer) and `scripts/version-pins.py bump-self aks vX.Y.Z` (`chartSourceUrl` in `main.bicep`, `azuredeploy.json` and
   `createUiDefinition.json`; then `az bicep build` as the AKS README says). A stack release cut without this deploys the previous
   release's code: `aks-stack-v1.0.13` named v1.0.12, and `eks-stack-v1.0.17` named v1.0.16 and had to be superseded. OKE and GKE have
   no self-pin: they are tag-only (GKE also deploys straight from `main`).
3. Tag at the merge commit and create the release with `--latest=false`, with the assets the previous release of that stack had:
   OKE `omnigateokestack-vX.Y.Z.zip`; EKS `omnigateeksstack-vX.Y.Z.zip`, plus `template.yaml` uploaded to
   `s3://thinkingsense-cfn-templates/eks-stack-vX.Y.Z/` (the Launch Stack link reads it there); AKS `azuredeploy.json` and
   `omnigateaksstack-vX.Y.Z.zip`; GKE `omnigategkestack-vX.Y.Z.zip`. Zip from `resource-manager/` so the stack directory is at the top of the zip (that is the layout the OCI docs page's
   `--working-directory omnigateokestack` expects): `cd resource-manager && zip -r omnigateokestack-vX.Y.Z.zip omnigateokestack`
   (do it on a checkout of the tag, and exclude `.DS_Store`).
4. `scripts/version-pins.py check --verify-tags` now passes (every self-pin names a tag that exists).
5. Update the docs site and open that PR **after** the releases exist, so no page links to an asset that is not there yet.

**Always pass `--latest=false` for stack tags.** App releases and stack releases share one GitHub
Releases list, and the app release should stay the repository's Latest. (Until v0.10.8 the stacks downloaded the app jar through `/releases/latest` to hash
passwords, so a stack release that became "latest" broke fresh deploys; they no longer do. Fix with
`gh release edit <app-tag> --repo thinkingsense-ai/Docker --latest`.)

**[proposed]** The hash step should download the jar for the image's base version (strip any
`-suffix`, so `v0.8.0-oracle-fix` uses `v0.8.0`) and fall back to latest only if no such release
exists. Today it falls back to latest for any non-release tag, so the pods can run 0.8 while the
password is hashed by 0.10.3.
