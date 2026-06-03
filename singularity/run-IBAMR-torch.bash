#!/usr/bin/env bash
# run-IBAMR-torch.bash — Run commands inside the IBAMR Apptainer container
#
# Usage:
#   bash singularity/run-IBAMR-torch.bash [command [args...]]
#
# With no arguments, drops into an interactive shell.
#
# Special sub-commands:
#   make-sim          Configure (cmake) and build the simulation in ./build/
#   make-sim-clean    Remove ./build/ and rebuild from scratch
#
# Examples:
#   bash singularity/run-IBAMR-torch.bash              # interactive shell
#   bash singularity/run-IBAMR-torch.bash make-sim     # build main2d
#   bash singularity/run-IBAMR-torch.bash mpirun -np 4 ./build/main2d input2d
#
# -------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SIF="${SCRIPT_DIR}/ibamr.sif"

if [[ ! -f "${SIF}" ]]; then
    echo "ERROR: Container not found: ${SIF}"
    echo "  Build it first:  bash singularity/build-container.sh"
    exit 1
fi

# Detect runtime
if command -v apptainer &>/dev/null; then
    RUNTIME=apptainer
elif command -v singularity &>/dev/null; then
    RUNTIME=singularity
else
    echo "ERROR: Neither 'apptainer' nor 'singularity' found in PATH."
    exit 1
fi

# -------------------------------------------------------------------------
# Special sub-commands
# -------------------------------------------------------------------------
if [[ "${1:-}" == "make-sim" || "${1:-}" == "make-sim-clean" ]]; then
    BUILD_DIR="${PROJECT_DIR}/build"
    if [[ "${1}" == "make-sim-clean" ]]; then
        rm -rf "${BUILD_DIR}"
    fi
    mkdir -p "${BUILD_DIR}"

    "${RUNTIME}" exec --bind "${PROJECT_DIR}":"${PROJECT_DIR}" "${SIF}" \
        /bin/bash -c "
            set -euo pipefail
            source /opt/ibamr/configuration/enable.sh
            cd '${BUILD_DIR}'
            cmake \
                -DCMAKE_C_COMPILER=/usr/bin/mpicc \
                -DCMAKE_CXX_COMPILER=/usr/bin/mpicxx \
                -DCMAKE_Fortran_COMPILER=/usr/bin/mpifort \
                -DIBAMR_ROOT=/opt/ibamr \
                '${PROJECT_DIR}'
            make -j\$(nproc)
        "
    echo "=== Build complete: ${BUILD_DIR}/main2d ==="
    exit 0
fi

# -------------------------------------------------------------------------
# General passthrough: run any command (or interactive shell) in container
# -------------------------------------------------------------------------
if [[ $# -eq 0 ]]; then
    # Interactive shell
    "${RUNTIME}" shell --bind "${PROJECT_DIR}":"${PROJECT_DIR}" "${SIF}"
else
    "${RUNTIME}" exec --bind "${PROJECT_DIR}":"${PROJECT_DIR}" "${SIF}" "$@"
fi
