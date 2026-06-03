#!/bin/bash
#SBATCH --job-name=ibamr-rotating-cylinder
#SBATCH --account=torch_pr_767_general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --mem=128G
#SBATCH --time=72:00:00
#SBATCH --output=%x-%j.out
#SBATCH --error=%x-%j.err

# -------------------------------------------------------------------------
# Usage (from the project root):
#   sbatch singularity/run-simulation.slurm
#   sbatch singularity/run-simulation.slurm input2d
#   sbatch singularity/run-simulation.slurm input2d restart_IB2d 5
#
# Outputs land in the run folder:
#   viz_cylinder2d/     VisIt/Silo visualization
#   cylinder_dump/      drag/force output
#   Dump--Cylinder/     constraint IB output
#   IB2d_cylinder2d.log
# -------------------------------------------------------------------------

set -euo pipefail

# Copy SLURM output/error files into the run folder when the job ends (success or failure)
RUN_DIR="${PWD}"
copy_slurm_logs() {
    local out="${SLURM_SUBMIT_DIR}/${SLURM_JOB_NAME}-${SLURM_JOB_ID}.out"
    local err="${SLURM_SUBMIT_DIR}/${SLURM_JOB_NAME}-${SLURM_JOB_ID}.err"
    sleep 2
    [[ -f "${out}" ]] && cp "${out}" "${RUN_DIR}/" && echo "Copied ${out##*/} → run folder"
    [[ -f "${err}" ]] && cp "${err}" "${RUN_DIR}/" && echo "Copied ${err##*/} → run folder"
}
trap copy_slurm_logs EXIT

# Paths are passed as env vars by setup_run.py via --export.
# IBAMR_PROJECT_DIR, IBAMR_SIF, IBAMR_EXECUTABLE must be set.
if [[ -z "${IBAMR_PROJECT_DIR:-}" ]]; then
    echo "ERROR: IBAMR_PROJECT_DIR not set. Submit via setup_run.py."
    exit 1
fi
PROJECT_DIR="${IBAMR_PROJECT_DIR}"
SIF="${IBAMR_SIF}"
EXECUTABLE="${IBAMR_EXECUTABLE}"

INPUT_FILE="${1:-input2d}"
RESTART_ARGS="${@:2}"   # optional: <restart_dir> <restart_num>

echo "=== IBAMR Rotating Cylinder 2D Simulation ==="
echo "  Job ID:      ${SLURM_JOB_ID}"
echo "  Node:        ${SLURMD_NODENAME}"
echo "  MPI tasks:   ${SLURM_NTASKS}"
echo "  Working dir: ${PROJECT_DIR}"
echo "  Input file:  ${INPUT_FILE}"
echo "  Container:   ${SIF}"
echo ""

srun apptainer exec \
    --bind "${PROJECT_DIR}":"${PROJECT_DIR}" \
    "${SIF}" \
    "${EXECUTABLE}" "${INPUT_FILE}" ${RESTART_ARGS}
