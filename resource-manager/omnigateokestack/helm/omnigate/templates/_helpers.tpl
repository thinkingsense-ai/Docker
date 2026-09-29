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
    checksum/configmap: {{ include (print .Template.BasePath "/configmap.yaml") . | sha256sum }}
spec:
  initContainers:
    - name: wait-for-postgres
      image: docker.io/library/postgres:16-alpine
      command:
        - sh
        - -c
        - until pg_isready -h {{ include "omnigate.postgresHost" . }} -U {{ .Values.postgres.user }}; do sleep 2; done
  containers:
    - name: omnigate
      image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
      imagePullPolicy: {{ .Values.image.pullPolicy }}
      envFrom:
        - configMapRef:
            name: {{ include "omnigate.fullname" . }}-omnigate-config
        - secretRef:
            name: {{ include "omnigate.fullname" . }}-omnigate-secret
      ports:
        - name: http
          containerPort: 8080
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
{{- if not .Values.omnigate.configDb.external }}
      volumeMounts:
        - name: data
          mountPath: /var/lib/omnigate/data
{{- end }}
      readinessProbe:
        httpGet:
          path: /
          port: 8080
        initialDelaySeconds: 15
        periodSeconds: 10
      resources:
        {{- toYaml .Values.resources.omnigate | nindent 8 }}
{{- if not .Values.omnigate.configDb.external }}
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: {{ include "omnigate.fullname" . }}-omnigate-data
{{- end }}
{{- end -}}
