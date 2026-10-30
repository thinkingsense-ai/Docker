{{- define "omnigate.fullname" -}}
{{- .Release.Name -}}
{{- end -}}

{{- define "omnigate.postgresHost" -}}
{{- printf "%s-postgres" (include "omnigate.fullname" .) -}}
{{- end -}}

{{- /* HTTPS modes: "custom" when a keystore is supplied, "auto" (a self-signed certificate made at first start) when HTTPS is on without one. */ -}}
{{- define "omnigate.tlsCustom" -}}{{- if and .Values.tls.enabled .Values.tls.keystore }}true{{ end -}}{{- end -}}
{{- define "omnigate.tlsAuto" -}}{{- if and .Values.tls.enabled (not .Values.tls.keystore) }}true{{ end -}}{{- end -}}
{{- define "omnigate.tlsDir" -}}{{- if .Values.omnigate.configDb.external }}/etc/omnigate-tls{{ else }}/var/lib/omnigate/data/tls{{ end -}}{{- end -}}

{{- define "omnigate.labels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: omnigate
{{- end -}}

{{- /*
Shared pod template (metadata + spec) for the omnigate container -- used by both the default
Deployment and the clusterEnabled StatefulSet in omnigate.yaml, so the two workload kinds don't
duplicate the whole container/env/volume spec. Call as
{{ include "omnigate.podTemplate" . | nindent 4 }} directly under a `template:` key.
*/ -}}
{{- define "omnigate.podTemplate" -}}
metadata:
  labels:
    app.kubernetes.io/instance: {{ .Release.Name }}
    app.kubernetes.io/component: omnigate
  annotations:
    # See the Deployment's own historical comment (still applies): envFrom vars are read once at
    # container start, so these checksums are what actually triggers a rollout when the rendered
    # Secret/ConfigMap content changes -- e.g. a `terraform apply` that only changes
    # omnigate_llm_api_key or image.tag.
    checksum/secret: {{ include (print .Template.BasePath "/secrets.yaml") . | sha256sum }}
{{- if include "omnigate.tlsCustom" . }}
    # The keystore is read once at startup, so a new certificate must roll the pods.
    checksum/tls: {{ include (print .Template.BasePath "/tls.yaml") . | sha256sum }}
{{- end }}
    checksum/configmap: {{ include (print .Template.BasePath "/configmap.yaml") . | sha256sum }}
spec:
  serviceAccountName: {{ include "omnigate.fullname" . }}-omnigate
  # The image runs as uid 10001 (since 0.10.11) and a cloud volume is owned by root, so without fsGroup the pod could not write
  # /var/lib/omnigate/data and the app would stop at startup. Kubernetes gives the volume this group (and group write), including a
  # volume an earlier release created as root, so an upgrade needs no manual chown. OnRootMismatch skips the recursive change on
  # a large volume that is already right.
  securityContext:
    fsGroup: 10001
    fsGroupChangePolicy: OnRootMismatch
{{- if gt (int .Values.omnigate.replicaCount) 1 }}
  # More than one replica: prefer to put them on different nodes, so one node going down (or being drained for maintenance) does not take every
  # replica with it. "Preferred", not "required": with fewer nodes than replicas the extra replicas still start (on a shared node) instead of
  # sitting Pending. Together with the PodDisruptionBudget (pdb.yaml) this is what keeps the app up through a node drain.
  affinity:
    podAntiAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 100
          podAffinityTerm:
            topologyKey: kubernetes.io/hostname
            labelSelector:
              matchLabels:
                app.kubernetes.io/instance: {{ .Release.Name }}
                app.kubernetes.io/component: omnigate
{{- end }}
{{- if and .Values.image.pullUsername .Values.image.pullAuthToken }}
  imagePullSecrets:
    - name: {{ include "omnigate.fullname" . }}-omnigate-imagepull
{{- end }}
  initContainers:
{{- if include "omnigate.tlsAuto" . }}
    # No certificate supplied: make a self-signed one for the load balancer's address, the first time (kept on the data volume, so it survives
    # restarts; made again if the address changes). The app rejects an HTTPS request whose Host is not named in the certificate ("Invalid SNI"), so the
    # address has to be in it: the first step reads it from the Service, the second makes the certificate with the image's own keytool. Browsers
    # show a "not trusted" warning for it until you supply your own certificate (tls.keystore).
    - name: tls-address
      image: docker.io/library/python:3.12-slim
      command:
        - python
        - -c
        - |
          import json, os, ssl, time, urllib.request
          b = "/var/run/secrets/kubernetes.io/serviceaccount/"
          tok = open(b + "token").read(); ns = open(b + "namespace").read()
          ctx = ssl.create_default_context(cafile=b + "ca.crt")
          url = "https://%s:%s/api/v1/namespaces/%s/services/{{ include "omnigate.fullname" . }}-omnigate-http" % (os.environ["KUBERNETES_SERVICE_HOST"], os.environ["KUBERNETES_SERVICE_PORT"], ns)
          addrs = []
          for _ in range(180):
              try:
                  req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
                  ing = json.load(urllib.request.urlopen(req, context=ctx, timeout=10)).get("status", {}).get("loadBalancer", {}).get("ingress", [])
                  addrs = sorted(x.get("ip") or x.get("hostname") for x in ing if x.get("ip") or x.get("hostname"))
              except Exception as e:
                  print("waiting for the load balancer address:", e)
              if addrs:
                  break
              time.sleep(5)
          open("/work/address", "w").write(" ".join(addrs))
          print("load balancer address(es):", addrs or "none yet; the certificate will not name one")
      volumeMounts:
        - name: tls-work
          mountPath: /work
    - name: tls-init
      image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
      imagePullPolicy: {{ .Values.image.pullPolicy }}
      command:
        - sh
        - -c
        - |
          D={{ include "omnigate.tlsDir" . }}
          mkdir -p $D
          A=$(cat /work/address 2>/dev/null || true)
          if [ -s $D/omnigate.p12 ] && [ "$(cat $D/address 2>/dev/null)" = "$A" ]; then exit 0; fi
          rm -f $D/omnigate.p12
          SAN="dns:omnigate,dns:localhost"
          for a in $A; do case "$a" in *[a-zA-Z]*) SAN="$SAN,dns:$a";; *) SAN="$SAN,ip:$a";; esac; done
          keytool -genkeypair -alias omnigate -keyalg RSA -keysize 2048 -validity 3650 -storetype PKCS12 -keystore $D/omnigate.p12 \
            -storepass omnigate-selfsigned -keypass omnigate-selfsigned -dname "CN=omnigate" -ext "san=$SAN"
          printf '%s' "$A" > $D/address
      volumeMounts:
        - name: tls-work
          mountPath: /work
{{- if .Values.omnigate.configDb.external }}
        - name: tls
          mountPath: /etc/omnigate-tls
{{- else }}
        - name: data
          mountPath: /var/lib/omnigate/data
{{- end }}
{{- end }}
    - name: wait-for-postgres
      image: docker.io/library/postgres:16-alpine
      command:
        - sh
        - -c
        - until pg_isready -h {{ include "omnigate.postgresHost" . }} -U {{ .Values.postgres.user }}; do sleep 2; done
{{- if .Values.tpch.enabled }}
    # The TPC-H backends are registered at startup, so the pod must not start until the loader has
    # finished. `orders` is loaded last, so a full-size orders table means everything is in place.
    - name: wait-for-tpch
      image: docker.io/library/postgres:16-alpine
      env:
        - name: PGPASSWORD
          valueFrom:
            secretKeyRef:
              name: {{ include "omnigate.fullname" . }}-postgres-secret
              key: POSTGRES_PASSWORD
      command:
        - sh
        - -c
        - >-
          until [ "$(psql -h {{ include "omnigate.postgresHost" . }} -U {{ .Values.postgres.user }} -d {{ .Values.tpch.database }} -tAc 'SELECT count(*) FROM orders' 2>/dev/null || echo 0)" -ge {{ int (mulf 1500000 .Values.tpch.scaleFactor) }} ]; do sleep 5; done
{{- end }}
{{- if .Values.manufacturingDemo.enabled }}
{{- include "omnigate.manufacturingDemoInit" . | nindent 4 }}
{{- end }}
{{- include "omnigate.readOnlyRoleInit" . | nindent 4 }}
  containers:
    - name: omnigate
      image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
      imagePullPolicy: {{ .Values.image.pullPolicy }}
      # Least privilege for the app container only (the init containers, such as the database one, have their own needs): the image runs as 10001 since
      # 0.10.11, so say so, and drop everything it does not need. The root filesystem is read-only; the JVM and DuckDB write under /tmp, which is a scratch volume.
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
        seccompProfile:
          type: RuntimeDefault
      envFrom:
        - configMapRef:
            name: {{ include "omnigate.fullname" . }}-omnigate-config
        - secretRef:
            name: {{ include "omnigate.fullname" . }}-omnigate-secret
      env:
        # The signed licence that lets the free image run as the commercial edition (thinkingsense-ai/Server#18). The app
        # re-reads this file every minute, so a renewed licence applies without a restart. It is a whole-directory Secret
        # mount (not subPath, which never updates) and the Secret is its own template (license.yaml), outside the checksum
        # annotation above, so changing it does not roll the pods.
        - name: OMNIGATE_LICENSE_FILE
          value: /etc/omnigate-license/license
{{- if include "omnigate.tlsCustom" . }}
        - name: OMNIGATE_TLS_KEYSTORE
          value: /etc/omnigate-tls/omnigate.p12
        - name: OMNIGATE_TLS_KEYSTORE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: {{ include "omnigate.fullname" . }}-omnigate-tls
              key: password
{{- else if include "omnigate.tlsAuto" . }}
        - name: OMNIGATE_TLS_KEYSTORE
          value: {{ include "omnigate.tlsDir" . }}/omnigate.p12
        - name: OMNIGATE_TLS_KEYSTORE_PASSWORD
          value: omnigate-selfsigned
{{- end }}
      ports:
        - name: http
          containerPort: 8080
{{- if .Values.tls.enabled }}
        - name: https
          containerPort: 8443
{{- end }}
        - name: oracle-wire
          containerPort: 1521
        - name: pg-wire
          containerPort: 5433
        - name: mysql-wire
          containerPort: 3306
        - name: grpc
          containerPort: 7070
{{- if .Values.omnigate.clusterEnabled }}
        - name: ignite-disco
          containerPort: 47500
        - name: ignite-comm
          containerPort: 47100
{{- end }}
      volumeMounts:
        - name: license
          mountPath: /etc/omnigate-license
          readOnly: true
{{- if include "omnigate.tlsCustom" . }}
        - name: tls
          mountPath: /etc/omnigate-tls
          readOnly: true
{{- else if and (include "omnigate.tlsAuto" .) .Values.omnigate.configDb.external }}
        - name: tls
          mountPath: /etc/omnigate-tls
          readOnly: true
{{- end }}
{{- if not .Values.omnigate.configDb.external }}
        - name: data
          mountPath: /var/lib/omnigate/data
        - name: tmp
          mountPath: /tmp
{{- end }}
      readinessProbe:
        httpGet:
          path: /
          port: 8080
        initialDelaySeconds: 15
        periodSeconds: 10
      resources:
        {{- toYaml .Values.resources.omnigate | nindent 8 }}
  volumes:
    - name: license
      secret:
        secretName: {{ include "omnigate.fullname" . }}-omnigate-license
        optional: true
{{- if include "omnigate.tlsCustom" . }}
    - name: tls
      secret:
        secretName: {{ include "omnigate.fullname" . }}-omnigate-tls
{{- else if and (include "omnigate.tlsAuto" .) .Values.omnigate.configDb.external }}
    - name: tls
      emptyDir: {}
{{- end }}
{{- if include "omnigate.tlsAuto" . }}
    - name: tls-work
      emptyDir: {}
{{- end }}
{{- if not .Values.omnigate.configDb.external }}
    - name: data
      persistentVolumeClaim:
        claimName: {{ include "omnigate.fullname" . }}-omnigate-data
    - name: tmp
      emptyDir: {}
{{- end }}
{{- end -}}

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
