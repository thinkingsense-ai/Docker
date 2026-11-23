{{- define "omnigate.fullname" -}}
{{- .Release.Name -}}
{{- end -}}

{{- define "omnigate.postgresHost" -}}
{{- printf "%s-postgres" (include "omnigate.fullname" .) -}}
{{- end -}}

{{- define "omnigate.labels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: omnigate
{{- end -}}

{{- /* HTTPS modes: "custom" when a keystore is supplied, "auto" (a self-signed certificate made at first start) when HTTPS is on without one. */ -}}
{{- define "omnigate.tlsCustom" -}}{{- if and .Values.tls.enabled .Values.tls.keystore }}true{{ end -}}{{- end -}}
{{- define "omnigate.tlsAuto" -}}{{- if and .Values.tls.enabled (not .Values.tls.keystore) }}true{{ end -}}{{- end -}}

{{- /*
Init container that makes sure the app's SELECT-only database account exists and has exactly SELECT on everything in the demo
database. Runs as the postgres superuser, on every pod start, so it works for a fresh stack (the database was just seeded) and
for one upgraded from a release that connected as the superuser (the data is already there). Idempotent; retried because two
replicas starting together can race on ALTER ROLE.
*/ -}}
{{- define "omnigate.readOnlyRoleInit" -}}
- name: ensure-readonly-role
  image: docker.io/library/postgres:16-alpine
  env:
    - name: PGHOST
      value: {{ include "omnigate.postgresHost" . | quote }}
    - name: PGDATABASE
      value: {{ .Values.postgres.database | quote }}
    - name: PGUSER
      valueFrom:
        secretKeyRef:
          name: {{ include "omnigate.fullname" . }}-postgres-secret
          key: POSTGRES_USER
    - name: PGPASSWORD
      valueFrom:
        secretKeyRef:
          name: {{ include "omnigate.fullname" . }}-postgres-secret
          key: POSTGRES_PASSWORD
    - name: RO_USER
      valueFrom:
        secretKeyRef:
          name: {{ include "omnigate.fullname" . }}-postgres-ro-secret
          key: PG_RO_USER
    - name: RO_PASSWORD
      valueFrom:
        secretKeyRef:
          name: {{ include "omnigate.fullname" . }}-postgres-ro-secret
          key: PG_RO_PASSWORD
  command:
    - sh
    - -c
    - |
      set -e
      cat > /tmp/readonly-role.sql <<'SQL'
      SELECT format('CREATE ROLE %I LOGIN', :'ro') WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'ro') \gexec
      SELECT format('ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L', :'ro', :'pw') \gexec
      SELECT format('ALTER ROLE %I SET default_transaction_read_only = on', :'ro') \gexec
      SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'ro') \gexec
      SELECT format('GRANT USAGE ON SCHEMA %I TO %I', nspname, :'ro') FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname <> 'information_schema' \gexec
      SELECT format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO %I', nspname, :'ro') FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname <> 'information_schema' \gexec
      SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT ON TABLES TO %I', nspname, :'ro') FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname <> 'information_schema' \gexec
      SQL
      until pg_isready; do sleep 2; done
      until psql -v ON_ERROR_STOP=1 -v ro="$RO_USER" -v pw="$RO_PASSWORD" -f /tmp/readonly-role.sql; do echo "retrying"; sleep 3; done
{{- end -}}

{{- /*
Adds the parts / bill of materials / supplier capability / quote tables to the three demo schemas (files/seed-manufacturing.sql).
Not part of the one-time Postgres seed, because that only runs on an empty data volume and a stack upgraded in place would never get
it (and would be offered trusted questions about tables that do not exist). Runs before ensure-readonly-role so its grants cover them.
*/ -}}
{{- define "omnigate.manufacturingDemoInit" -}}
- name: ensure-manufacturing-demo
  image: docker.io/library/postgres:16-alpine
  env:
    - name: PGHOST
      value: {{ include "omnigate.postgresHost" . | quote }}
    - name: PGDATABASE
      value: {{ .Values.postgres.database | quote }}
    - name: PGUSER
      valueFrom:
        secretKeyRef:
          name: {{ include "omnigate.fullname" . }}-postgres-secret
          key: POSTGRES_USER
    - name: PGPASSWORD
      valueFrom:
        secretKeyRef:
          name: {{ include "omnigate.fullname" . }}-postgres-secret
          key: POSTGRES_PASSWORD
    - name: MFG_SQL
      valueFrom:
        configMapKeyRef:
          name: {{ include "omnigate.fullname" . }}-seed-manufacturing
          key: seed-manufacturing.sql
  command:
    - sh
    - -c
    - |
      set -e
      until pg_isready; do sleep 2; done
      # Only when the tables are not there yet and the three demo schemas are (a database that was replaced is left alone).
      todo=$(psql -tAc "SELECT to_regclass('inventory.parts') IS NULL AND to_regclass('suppliers.suppliers') IS NOT NULL AND to_regclass('inventory.warehouse_inventory') IS NOT NULL AND to_regclass('procurement.purchase_orders') IS NOT NULL")
      if [ "$todo" = t ]; then
        until printf '%s\n' "$MFG_SQL" | psql -v ON_ERROR_STOP=1 -1 -f -; do echo "retrying"; sleep 3; done
      fi
{{- end -}}

{{- define "omnigate.mariadbHost" -}}
{{- printf "%s-mariadb" (include "omnigate.fullname" .) -}}
{{- end -}}

{{- /*
Waits for the MariaDB half of the IT & operational risk pack. The app registers its data sources at startup, so it must not start before
the database accepts connections. `mariadb-admin ping` exits 0 whenever the server answers, even if it refuses the login, and a server
still running its first-time setup only listens on a local socket, so a TCP answer means the real server is up. `--skip-ssl`
is needed: the 11.x client checks the server's certificate by default and the image's is self-signed, so without it the
command exits 1 and this container waits forever (found in the first live deploy).
*/ -}}
{{- define "omnigate.mariadbWaitInit" -}}
- name: wait-for-mariadb
  image: {{ .Values.mariadb.image }}
  command:
    - sh
    - -c
    - until mariadb-admin ping -h {{ include "omnigate.mariadbHost" . }} --silent --skip-ssl; do sleep 2; done
{{- end -}}

{{- /* The all-packs demo set: every demo pack at once (supply chain, manufacturing, IT & operational risk, Smithsonian). */ -}}
{{- define "omnigate.packs" -}}{{- if or (eq (include "omnigate.dataset" .) "all-packs") (eq (include "omnigate.dataset" .) "mix") }}true{{ end -}}{{- end -}}
{{- /* The MariaDB database (`security`) is part of the IT & operational risk pack, on its own or inside all-packs. */ -}}
{{- define "omnigate.hasMariadb" -}}{{- if or (eq (include "omnigate.dataset" .) "it-risk") (eq (include "omnigate.dataset" .) "treasury") (eq (include "omnigate.dataset" .) "all-packs") (and (eq (include "omnigate.dataset" .) "mix") (or (include "omnigate.has" (dict "ctx" . "pack" "it-risk")) (include "omnigate.has" (dict "ctx" . "pack" "treasury")))) }}true{{ end -}}{{- end -}}
{{- define "omnigate.embedHost" -}}
{{- printf "%s-packs-embed" (include "omnigate.fullname" .) -}}
{{- end -}}
{{- define "omnigate.s3Host" -}}
{{- printf "%s-packs-s3" (include "omnigate.fullname" .) -}}
{{- end -}}

{{- /*
Waits for the all-packs demo's two loads: the Smithsonian table in Postgres (created in one transaction by the packs-loader Job, so its
existence means every row is in) and the museum directory in the object store. The app registers its data sources at startup, so it
must not start before both are there. Runs before ensure-readonly-role so that role's SELECT grants cover the smithsonian schema.
*/ -}}
{{- define "omnigate.packsWaitInit" -}}
- name: wait-for-packs-data
  image: docker.io/library/postgres:16-alpine
  env:
    - name: PGHOST
      value: {{ include "omnigate.postgresHost" . | quote }}
    - name: PGDATABASE
      value: {{ .Values.postgres.database | quote }}
    - name: PGUSER
      valueFrom:
        secretKeyRef:
          name: {{ include "omnigate.fullname" . }}-postgres-secret
          key: POSTGRES_USER
    - name: PGPASSWORD
      valueFrom:
        secretKeyRef:
          name: {{ include "omnigate.fullname" . }}-postgres-secret
          key: POSTGRES_PASSWORD
  command:
    - sh
    - -c
    - |
      until [ "$(psql -tAc "SELECT to_regclass('smithsonian.si_topics') IS NOT NULL" 2>/dev/null)" = t ]; do echo "waiting for the Smithsonian table"; sleep 3; done
      until wget -q -O /dev/null http://{{ include "omnigate.s3Host" . }}:9000/{{ .Values.packs.bucket }}/museums.csv; do echo "waiting for the museum directory"; sleep 3; done
      until wget -q -O /dev/null http://{{ include "omnigate.embedHost" . }}:8090/health; do echo "waiting for the embedding model"; sleep 3; done
{{- end -}}

{{- /* Standalone demo sets that replace the supply-chain data: it-risk, bom (BOM / sourcing), treasury (cash, payables, hedges, debt). */ -}}
{{- define "omnigate.standalone" -}}{{- if or (eq (include "omnigate.dataset" .) "it-risk") (eq (include "omnigate.dataset" .) "bom") (eq (include "omnigate.dataset" .) "treasury") }}true{{ end -}}{{- end -}}
{{- /* The MariaDB database the app reads: `erp` for the treasury pack, `security` for the IT & operational risk pack. */ -}}
{{- define "omnigate.mariadbDatabase" -}}{{ ternary "erp" "security" (eq (include "omnigate.erpOnly" .) "true") }}{{- end -}}
{{- define "omnigate.mariadbSeedName" -}}{{ ternary "seed-treasury-mariadb" "seed-it-risk-mariadb" (eq (include "omnigate.erpOnly" .) "true") }}{{- end -}}
{{- define "omnigate.postgresSeedName" -}}{{- if include "omnigate.packs" . }}seed-packs-postgres{{ else if eq (include "omnigate.dataset" .) "it-risk" }}seed-it-risk-postgres{{ else if eq (include "omnigate.dataset" .) "bom" }}seed-bom-postgres{{ else if eq (include "omnigate.dataset" .) "treasury" }}seed-treasury-postgres{{ else }}seed-supply-chain{{ end -}}{{- end -}}

{{- /* The embedding model Deployment and question matching (approved questions served from their saved SQL): all-packs, and the bom and treasury sets. */ -}}
{{- define "omnigate.embedding" -}}{{- if or (eq (include "omnigate.dataset" .) "all-packs") (eq (include "omnigate.dataset" .) "bom") (eq (include "omnigate.dataset" .) "treasury") (and (eq (include "omnigate.dataset" .) "mix") (or (include "omnigate.has" (dict "ctx" . "pack" "bom")) (include "omnigate.has" (dict "ctx" . "pack" "treasury")) (include "omnigate.has" (dict "ctx" . "pack" "agency-risk")))) }}true{{ end -}}{{- end -}}
{{- /* Waits for the embedding model to answer before the app starts (the bom and treasury sets; all-packs has this inside packsWaitInit). */ -}}
{{- define "omnigate.embedWaitInit" -}}
- name: wait-for-embedding-model
  image: docker.io/library/postgres:16-alpine
  command:
    - sh
    - -c
    - until wget -q -O /dev/null http://{{ include "omnigate.embedHost" . }}:8090/health; do echo "waiting for the embedding model"; sleep 3; done
{{- end -}}

{{- /*
Pack selection (phase 6). `demoDatasets` is a list of packs; when it is empty the single `demoDataset` string rules, exactly as before. A selection is checked, put in a
fixed order, and mapped back onto the five configurations the charts always had where it equals one: `omnigate.dataset` answers supply-chain, it-risk, bom, treasury or
all-packs for those, and "mix" for any other combination, which is deployed the all-packs way (one connector per kind, schemas discovered) holding only the chosen packs.
*/ -}}
{{- define "omnigate.selection" -}}
{{- if .Values.demoDatasets -}}
{{- $known := list "supply-chain" "manufacturing" "it-risk" "smithsonian" "bom" "treasury" "agency-risk" -}}
{{- $sel := list -}}
{{- range .Values.demoDatasets -}}
{{- if not (has . $known) -}}{{- fail (printf "demoDatasets: %q is not a pack the charts can deploy (known: %s)" . (join ", " $known)) -}}{{- end -}}
{{- $sel = append $sel . -}}
{{- end -}}
{{- if and (has "manufacturing" $sel) (not (has "supply-chain" $sel)) -}}{{- $sel = append $sel "supply-chain" -}}{{- end -}}
{{- /* agency-risk (the Agency IT-risk investigation data: schemas rca, estate, register) reads beside the IT and operational risk pack, so it brings that pack in. */ -}}
{{- if and (has "agency-risk" $sel) (not (has "it-risk" $sel)) -}}{{- $sel = append $sel "it-risk" -}}{{- end -}}
{{- $out := list -}}
{{- range $known -}}{{- if has . $sel -}}{{- $out = append $out . -}}{{- end -}}{{- end -}}
{{- if and (has "smithsonian" $out) (ne (len (without $out "agency-risk")) 6) -}}{{- fail "demoDatasets: the Smithsonian pack (object store, loader, vocabulary) is only deployed together with all six packs for now; leave it out of a smaller selection or select every pack" -}}{{- end -}}
{{- toJson $out -}}
{{- end -}}
{{- end -}}

{{- define "omnigate.dataset" -}}
{{- $sel := include "omnigate.selection" . -}}
{{- if not $sel -}}{{ .Values.demoDataset }}
{{- else -}}
{{- $l := $sel | fromJsonArray -}}
{{- if and (eq (len $l) 6) (not (has "agency-risk" $l)) -}}all-packs
{{- else if and (eq (len $l) 1) (has (first $l) (list "supply-chain" "it-risk" "bom" "treasury")) -}}{{ first $l }}
{{- else if and (has "supply-chain" $l) (le (len $l) 2) (not (has "it-risk" $l)) (not (has "bom" $l)) (not (has "treasury" $l)) -}}supply-chain
{{- else -}}mix
{{- end -}}
{{- end -}}
{{- end -}}

{{- /* Is this pack part of the deployment? Called as (include "omnigate.has" (dict "ctx" . "pack" "bom")). Prints "true" or nothing. */ -}}
{{- define "omnigate.has" -}}
{{- $sel := include "omnigate.selection" .ctx -}}
{{- if $sel -}}{{- if has .pack ($sel | fromJsonArray) -}}true{{- end -}}
{{- else if and (eq .ctx.Values.demoDataset "all-packs") (ne .pack "agency-risk") -}}true
{{- else if eq .ctx.Values.demoDataset .pack -}}true
{{- end -}}
{{- end -}}

{{- /* Manufacturing tables and questions: with a selection, whether manufacturing is in it; without one, the old `manufacturingDemo.enabled` on the data sets that are not standalone. */ -}}
{{- define "omnigate.manufacturing" -}}
{{- if include "omnigate.selection" . -}}{{ include "omnigate.has" (dict "ctx" . "pack" "manufacturing") }}
{{- else if and .Values.manufacturingDemo.enabled (not (include "omnigate.standalone" .)) -}}true
{{- end -}}
{{- end -}}

{{- /* The object store, loader and Smithsonian vocabulary: all-packs only for now. */ -}}
{{- define "omnigate.hasSmithsonian" -}}{{- if and (include "omnigate.packs" .) (include "omnigate.has" (dict "ctx" . "pack" "smithsonian")) }}true{{ end -}}{{- end -}}

{{- /* The Treasury pack without the IT & risk pack: the MariaDB holds only `erp`. */ -}}
{{- define "omnigate.erpOnly" -}}{{- if or (eq (include "omnigate.dataset" .) "treasury") (and (eq (include "omnigate.dataset" .) "mix") (include "omnigate.has" (dict "ctx" . "pack" "treasury")) (not (include "omnigate.has" (dict "ctx" . "pack" "it-risk")))) }}true{{ end -}}{{- end -}}

{{- /* The schemas the federation planner may discover, in the order the all-packs set always listed them. */ -}}
{{- define "omnigate.federationSchemas" -}}
{{- $out := list -}}
{{- range $p := list (list "suppliers" "supply-chain") (list "inventory" "supply-chain") (list "procurement" "supply-chain") (list "risk" "it-risk") (list "smithsonian" "smithsonian") (list "security" "it-risk") (list "museums" "smithsonian") (list "bom" "bom") (list "treasury" "treasury") (list "erp" "treasury") (list "rca" "agency-risk") (list "estate" "agency-risk") (list "register" "agency-risk") -}}
{{- if include "omnigate.has" (dict "ctx" $ "pack" (index $p 1)) -}}{{- $out = append $out (index $p 0) -}}{{- end -}}
{{- end -}}
{{- join "," $out -}}
{{- end -}}
