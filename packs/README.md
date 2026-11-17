# Pack manifests

One `pack.json` per demo pack describes it once: title, summary, the sources and schemas it uses, its seeds and approved-question file, modalities,
editions, licence and capabilities. This is phase 1 of [docs/agency-design.md](../docs/agency-design.md); the design explains why a pack is a Workspace.

Nothing reads these files yet. No chart, compose file or form changed, so deployed behaviour is identical. They are the shared description that the
deploy forms, the Ask/Agency picker and Claude's tools will read in later phases.

| File | What |
|---|---|
| `<id>/pack.json` | The hand-written manifest |
| `catalogue.json` | Generated: manifests plus counts computed from the seeds and question files (tables, approved questions, questions joining two sources) |
| `workspaces.yaml` | Generated: an `all-data` Workspace (every backend) plus one per pack in the all-packs stack. Load it with the admin call `PUT /api/config/groups` and body `{"yaml": ...}`; it is a config-store key, not an environment variable. Without `all-data` the Server's Default workspace is empty once every backend is grouped |
| `test_packs.py` | Tests |

```bash
python3 scripts/packs.py check       # validate and confirm the generated files are current
python3 scripts/packs.py generate    # rewrite catalogue.json and workspaces.yaml after editing a manifest
python3 -m unittest discover -s packs
```

`check` fails if a pack's approved question uses a source or schema its manifest does not declare, if a listed seed is missing, or if a generated file is stale.

Known limits:
- A Workspace scopes by backend only, and the packs share one Postgres connector, so `workspaces.yaml` does not yet separate packs from each other. The catalogue's
  `sources[].schemas` records the intended scope until the Server supports schema-level Workspaces.
- `tables` is null for `smithsonian` (its tables are loaded by a script, not counted from a SQL seed). `manufacturing` counts only the tables it adds to the
  supply-chain schemas.
- `workspaces.yaml` has not been loaded into a running Server; the file parses as YAML and uses the keys `NamespaceConfig` reads (`id`, `name`, `backends`).
- `sounds` is Docker-only and has non-commercial data; it is in the catalogue but not in `workspaces.yaml`.
