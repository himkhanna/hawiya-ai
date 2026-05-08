#!/usr/bin/env bash
# Build an offline-installable Hawiya AI bundle.
#
# Output: dist/hawiya-ai-airgap-<version>.tar.gz containing:
#   image/hawiya-ai-<version>.tar          (docker save output)
#   chart/hawiya-ai-<version>.tgz          (helm package output)
#   install.sh                              (target-side installer)
#   README.md                               (operator notes)
#
# Phase 1 status: usable scaffold. Week 5 hardens this for Moro Hub
# (signed bundle, wheel cache for Phase 2 LLM workers, etc.).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

VERSION="$(awk -F'"' '/^version =/ {print $2; exit}' pyproject.toml)"
IMAGE="hawiya-ai:${VERSION}"
WORK_DIR="$(mktemp -d)"
BUNDLE_DIR="${WORK_DIR}/hawiya-ai-airgap-${VERSION}"
OUT_DIR="${ROOT_DIR}/dist"
OUT_TAR="${OUT_DIR}/hawiya-ai-airgap-${VERSION}.tar.gz"

echo "Hawiya AI air-gap bundle — version ${VERSION}"
mkdir -p "${BUNDLE_DIR}/image" "${BUNDLE_DIR}/chart" "${OUT_DIR}"

echo "[1/4] docker build ${IMAGE}"
docker build -t "${IMAGE}" -f deploy/Dockerfile .

echo "[2/4] docker save → image/"
docker save "${IMAGE}" -o "${BUNDLE_DIR}/image/hawiya-ai-${VERSION}.tar"

echo "[3/4] helm package → chart/"
helm package deploy/helm/hawiya-ai --destination "${BUNDLE_DIR}/chart"

echo "[4/4] assemble installer + README"
cp deploy/air-gap/install.sh "${BUNDLE_DIR}/install.sh"
cp deploy/air-gap/README.md "${BUNDLE_DIR}/README.md"
chmod +x "${BUNDLE_DIR}/install.sh"

tar -czf "${OUT_TAR}" -C "${WORK_DIR}" "hawiya-ai-airgap-${VERSION}"
rm -rf "${WORK_DIR}"

echo
echo "Bundle written:"
echo "  ${OUT_TAR}"
ls -lh "${OUT_TAR}"
