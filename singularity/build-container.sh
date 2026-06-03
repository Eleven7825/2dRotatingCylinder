#!/usr/bin/env bash
# build-container.sh — Build the IBAMR Singularity/Apptainer container
#
# This script is self-contained and reproducible on any HPC system that
# has Apptainer (or Singularity) installed.
#
# Usage:
#   bash singularity/build-container.sh [output.sif]
#
# The build requires write access to the filesystem and either:
#   - Root privileges, OR
#   - Apptainer --fakeroot support (common on HPC clusters), OR
#   - Submission as a build job (see SLURM section at the bottom).
#
# Output:  singularity/ibamr.sif  (or the path you specify)
#
# Estimated build time: 1-3 hours depending on CPU count and network speed.
# -------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEF_FILE="${SCRIPT_DIR}/ibamr.def"
SIF_FILE="${1:-${SCRIPT_DIR}/ibamr.sif}"

echo "=== IBAMR container build ==="
echo "  Definition:  ${DEF_FILE}"
echo "  Output SIF:  ${SIF_FILE}"
echo ""

# Detect apptainer vs singularity
if command -v apptainer &>/dev/null; then
    RUNTIME=apptainer
elif command -v singularity &>/dev/null; then
    RUNTIME=singularity
else
    echo "ERROR: Neither 'apptainer' nor 'singularity' found in PATH."
    echo "  On NYU Torch:   module load apptainer"
    echo "  On NYU Greene:  export PATH=/share/apps/singularity/bin:\$PATH"
    exit 1
fi
echo "Using runtime: ${RUNTIME}"

# -------------------------------------------------------------------------
# NYU Torch / Greene: load the module if available
# -------------------------------------------------------------------------
if [[ -n "${LMOD_CMD:-}" ]]; then
    module load apptainer 2>/dev/null || module load singularity 2>/dev/null || true
fi

# -------------------------------------------------------------------------
# Build strategy: try fakeroot first, fall back to --sandbox approach
# -------------------------------------------------------------------------
BUILD_CMD=("${RUNTIME}" build --fakeroot "${SIF_FILE}" "${DEF_FILE}")
[[ "${EUID}" -eq 0 ]] && BUILD_CMD=("${RUNTIME}" build "${SIF_FILE}" "${DEF_FILE}")

echo "=== Building (APPTAINER_BINDPATH cleared for build) ==="
# Clear APPTAINER_BINDPATH so the cluster's auto-bind list doesn't try to
# mount host paths that don't yet exist in the container image.
APPTAINER_BINDPATH="" SINGULARITY_BINDPATH="" "${BUILD_CMD[@]}"

echo ""
echo "=== Build complete ==="
echo "  Container:  ${SIF_FILE}"
echo ""
echo "Next steps:"
echo "  1. Compile the simulation (once, from the project root):"
echo "       bash singularity/run-IBAMR-torch.bash make-sim"
echo ""
echo "  2. Run the simulation:"
echo "       bash singularity/run-IBAMR-torch.bash mpirun -np 4 ./main3d input3d"
echo ""

# -------------------------------------------------------------------------
# SLURM job template — use this on clusters that forbid building on login nodes
# -------------------------------------------------------------------------
cat <<'SLURM'

# To build inside a SLURM job (recommended on busy HPC systems), submit:
#
#   sbatch singularity/build-container-job.slurm
#
# Or create the job file on the fly:
#
# sbatch --wrap="bash singularity/build-container.sh" \
#        --job-name=build-ibamr-sif \
#        --time=4:00:00 \
#        --mem=32G \
#        --cpus-per-task=8 \
#        --output=build-ibamr-%j.log

SLURM
