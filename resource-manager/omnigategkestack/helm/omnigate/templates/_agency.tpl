{{- /* Single source: agency/chart/_agency.tpl (copied into the four charts by scripts/sync-agency-addon.py). Which workflow engine the app is wired to: the Agency one, the payment-workflow gateway, or none. */ -}}
{{- define "omnigate.agencyWorkflows" -}}{{- if and .Values.agency.enabled .Values.agency.workflows.enabled }}true{{ end -}}{{- end -}}
{{- define "omnigate.engineName" -}}{{- if include "omnigate.agencyWorkflows" . }}agency-workflows{{ else if and .Values.paymentWorkflow.enabled .Values.paymentWorkflow.gateway.enabled }}payment-workflow{{ end -}}{{- end -}}
{{- define "omnigate.engineManifest" -}}{{ include "omnigate.fullname" . }}{{ if include "omnigate.agencyWorkflows" . }}-agency-workflows-manifest{{ else }}-workflow-manifest{{ end }}{{- end -}}
