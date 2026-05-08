# Hawiya AI Helm chart

Minimal but production-shaped chart for deploying Hawiya AI to Kubernetes.

```bash
# Lint locally
helm lint deploy/helm/hawiya-ai

# Render manifests without applying
helm template hawiya deploy/helm/hawiya-ai

# Install (kind / dev)
helm install hawiya deploy/helm/hawiya-ai

# Production
helm install hawiya deploy/helm/hawiya-ai \
  -f production-values.yaml \
  --namespace hawiya \
  --create-namespace
```

## Values overview

| Key | Default | Notes |
|-----|---------|-------|
| `image.repository` | `hawiya-ai` | Set to your internal registry path. |
| `image.tag` | `0.1.0` | Pin to a digest in production. |
| `replicaCount` | `2` | |
| `app.env` | `prod` | `dev` / `staging` / `prod` |
| `app.otel.exporterEndpoint` | `""` | OTLP/gRPC URL; empty disables export |
| `secrets.existingDatabaseSecret` | `""` | Recommended in production |
| `secrets.existingAuthSecret` | `""` | Recommended in production |
| `serviceMonitor.enabled` | `false` | Requires Prometheus Operator |
| `ingress.enabled` | `false` | TLS-terminating ingress recommended |

See `values.yaml` for the full list. Production deployments should always
pass `-f production-values.yaml` rather than editing `values.yaml`.
