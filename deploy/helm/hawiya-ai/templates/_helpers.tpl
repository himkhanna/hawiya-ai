{{/* Generic helpers used by every template. */}}

{{- define "hawiya.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "hawiya.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "hawiya.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "hawiya.labels" -}}
helm.sh/chart: {{ include "hawiya.chart" . }}
app.kubernetes.io/name: {{ include "hawiya.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "hawiya.selectorLabels" -}}
app.kubernetes.io/name: {{ include "hawiya.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "hawiya.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "hawiya.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/* Resolve the secret to mount for DB / bearer. Either existing or our own. */}}
{{- define "hawiya.databaseSecretName" -}}
{{- if .Values.secrets.existingDatabaseSecret -}}
{{- .Values.secrets.existingDatabaseSecret -}}
{{- else -}}
{{- printf "%s-database" (include "hawiya.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "hawiya.authSecretName" -}}
{{- if .Values.secrets.existingAuthSecret -}}
{{- .Values.secrets.existingAuthSecret -}}
{{- else -}}
{{- printf "%s-auth" (include "hawiya.fullname" .) -}}
{{- end -}}
{{- end -}}
