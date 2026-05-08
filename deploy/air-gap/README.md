# Hawiya AI — air-gap install bundle

Sovereign deployments operate without internet access at runtime
(CLAUDE.md §2). The air-gap bundle packages every artifact the target
cluster needs into a single tarball.

## Build (build side, has internet)

From the repo root:

```bash
make build-airgap
# → dist/hawiya-ai-airgap-<version>.tar.gz
```

The bundle contains:

| Path | Purpose |
|---|---|
| `image/hawiya-ai-<version>.tar` | `docker save` of the API image |
| `chart/hawiya-ai-<version>.tgz` | `helm package` of the chart |
| `install.sh` | target-side installer |
| `README.md` | this file |

Transfer `hawiya-ai-airgap-<version>.tar.gz` to the target environment
through whatever sneakernet mechanism the customer accepts (USB, SFTP
through a DMZ, etc.).

## Install (target side, air-gapped)

Prerequisites on the target:
- A Kubernetes cluster reachable from the bastion you run `install.sh` on
- A container registry that the cluster can pull from
- `docker`, `kubectl`, and `helm` installed locally
- Postgres provisioned and reachable (see `docs/deployment/kubernetes.md`)
- Secrets created out-of-band (`hawiya-database`, `hawiya-auth`)

```bash
tar -xf hawiya-ai-airgap-<version>.tar.gz
cd hawiya-ai-airgap-<version>

./install.sh \
  --registry your-internal.registry.local \
  --namespace hawiya \
  --values /path/to/production-values.yaml
```

The installer:
1. Loads the saved image into the local Docker daemon.
2. Retags to `<registry>/hawiya-ai:<version>` and pushes.
3. Creates the namespace (idempotent).
4. Runs `helm upgrade --install` with the chart, image overrides, and
   your values file.

## Phase 1 caveats

- **No wheel cache yet.** Phase 2 LLM workers will require offline
  Python wheels; this bundle doesn't ship them. Add as a follow-up.
- **No signature verification.** Production releases should sign the
  bundle and verify on install. Customer security review may add Cosign
  + sigstore here before sign-off.
- **Single image only.** Multi-arch (amd64 + arm64) bundles aren't
  supported yet — build twice and ship two bundles if needed.
- **Postgres is out of scope.** The bundle does not provision the
  database. Customers either manage Postgres themselves or run
  CloudNativePG; either way that's a separate workflow.

Phase 1 week 5 (Moro Hub deployment) hardens the items above.
