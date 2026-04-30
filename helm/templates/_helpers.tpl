{{/*
Expand the name of the chart.
*/}}
{{- define "dmarc-dashboard.fullname" -}}
{{- printf "%s" .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
