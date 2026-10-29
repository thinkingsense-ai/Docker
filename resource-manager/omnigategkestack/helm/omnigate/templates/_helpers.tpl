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
