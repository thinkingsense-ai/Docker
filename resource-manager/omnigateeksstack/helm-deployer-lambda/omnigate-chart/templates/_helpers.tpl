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
