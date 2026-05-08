#!/usr/bin/env bash
# Target-side installer for the Hawiya AI air-gap bundle.
#
# Usage:
#   ./install.sh --registry <internal.registry.local[:port]> \
#                [--namespace hawiya] \
#                [--values production-values.yaml]
#
# What it does:
#   1. Loads the saved image into the local Docker daemon.
#   2. Re-tags the image to ``<registry>/hawiya-ai:<version>`` and pushes.
#   3. Helms-installs the chart, wiring `image.repository` to the registry.
#
# Phase 1 caveat: this script does NOT manage Postgres provisioning,
# secret creation, or Prometheus wiring — see docs/deployment/kubernetes.md
# in the bundle for the full procedure.

set -euo pipefail

NAMESPACE="hawiya"
VALUES_FILE=""
REGISTRY=""
RELEASE_NAME="hawiya"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --registry) REGISTRY="$2"; shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --values) VALUES_FILE="$2"; shift 2 ;;
    --release) RELEASE_NAME="$2"; shift 2 ;;
    -h|--help)
      grep '^#' "$0" | head -20 | sed 's/^# \?//'
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "${REGISTRY}" ]]; then
  echo "ERROR: --registry is required" >&2
  exit 2
fi

BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_TAR="$(ls "${BUNDLE_DIR}"/image/hawiya-ai-*.tar | head -1)"
CHART_TGZ="$(ls "${BUNDLE_DIR}"/chart/hawiya-ai-*.tgz | head -1)"

if [[ ! -f "${IMAGE_TAR}" || ! -f "${CHART_TGZ}" ]]; then
  echo "ERROR: bundle is incomplete (image or chart missing)" >&2
  exit 1
fi

VERSION="$(basename "${IMAGE_TAR}" .tar | sed 's/^hawiya-ai-//')"
SRC_IMAGE="hawiya-ai:${VERSION}"
DEST_IMAGE="${REGISTRY}/hawiya-ai:${VERSION}"

echo "Hawiya AI air-gap install — version ${VERSION}"
echo "  Registry  : ${REGISTRY}"
echo "  Namespace : ${NAMESPACE}"
echo "  Release   : ${RELEASE_NAME}"
echo

echo "[1/4] docker load"
docker load -i "${IMAGE_TAR}"

echo "[2/4] retag and push to ${DEST_IMAGE}"
docker tag "${SRC_IMAGE}" "${DEST_IMAGE}"
docker push "${DEST_IMAGE}"

echo "[3/4] kubectl create namespace (idempotent)"
kubectl get ns "${NAMESPACE}" >/dev/null 2>&1 || kubectl create ns "${NAMESPACE}"

echo "[4/4] helm install"
HELM_ARGS=("upgrade" "--install" "${RELEASE_NAME}" "${CHART_TGZ}"
           "--namespace" "${NAMESPACE}"
           "--set" "image.repository=${REGISTRY}/hawiya-ai"
           "--set" "image.tag=${VERSION}")
if [[ -n "${VALUES_FILE}" ]]; then
  HELM_ARGS+=("-f" "${VALUES_FILE}")
fi
helm "${HELM_ARGS[@]}"

echo
echo "Done. Verify with:"
echo "  kubectl -n ${NAMESPACE} rollout status deploy/${RELEASE_NAME}"
echo "  kubectl -n ${NAMESPACE} port-forward svc/${RELEASE_NAME} 8000:80"
echo "  curl http://localhost:8000/v1/health"
