# 2D Rotating Cylinder — IBAMR Simulation

Immersed boundary simulation of a 2D rotating cylinder (rotobot) in viscous flow, built with [IBAMR](https://ibamr.github.io/).

---

## Prerequisites

- NYU **Torch** HPC cluster (or any system with Apptainer ≥ 1.2 and SLURM)
- Git, Python 3 — both available on Torch login nodes
- No local IBAMR installation needed — everything runs inside a container

---

## Quick Start (first time)

### 1 — Clone the repo

```bash
git clone https://github.com/Eleven7825/2dRotatingCylinder.git
cd 2dRotatingCylinder
```

### 2 — Build the Singularity container

This step compiles IBAMR and all dependencies inside a container. It runs **once** and takes 1–3 hours.

```bash
module load apptainer

sbatch --job-name=build-ibamr \
       --time=4:00:00 --mem=32G --cpus-per-task=8 \
       --output=build-%j.log \
       --wrap="bash singularity/build-container.sh"
```

Wait for the job to finish:

```bash
squeue -u $USER          # shows running jobs
cat build-<jobid>.log    # check progress / errors
```

The container is written to `singularity/ibamr.sif`.

### 3 — Compile the simulation

```bash
bash singularity/run-IBAMR-torch.bash make-sim
```

Runs `cmake` + `make` inside the container. Binary lands at `build/main2d`.

### 4 — Set up and submit a run

```bash
python3 setup_run.py
```

The script:
1. Creates a timestamped run folder in the project root (e.g., `2026-05-19_10-30-00/`)
2. Generates the cylinder surface mesh (`Cylinder2d.py`)
3. Copies input files into the run folder
4. Submits the SLURM job

Monitor the job:

```bash
squeue -u $USER
tail -f 2026-05-19_10-30-00/ibamr-rotating-cylinder-<jobid>.out
```

Cancel if needed:

```bash
scancel <jobid>
```

### 5 — Visualize results

Output appears inside the run folder:

| Directory | Contents |
|-----------|----------|
| `viz_cylinder2d/` | VisIt/Silo visualization data |
| `cylinder_dump/` | Drag / force time series |
| `Dump--Cylinder/` | Constraint IB output |

Open `viz_cylinder2d/` in [VisIt](https://visit-dav.github.io/visit-website/).

---

## Interactive run (no SLURM)

For quick tests or debugging, run directly in the container on the login node:

```bash
bash singularity/run-IBAMR-torch.bash mpirun -np 4 ./build/main2d input2d
```

Drop into an interactive shell inside the container:

```bash
bash singularity/run-IBAMR-torch.bash
```

---

## Restarting a simulation

Pass the restart directory and step number as extra arguments:

```bash
sbatch --chdir=<run-folder> \
       --export=ALL,IBAMR_PROJECT_DIR=$(pwd),IBAMR_SIF=singularity/ibamr.sif,IBAMR_EXECUTABLE=build/main2d \
       singularity/run-simulation.slurm input2d restart_IB2d <step>
```

---

## File overview

| File | Purpose |
|------|---------|
| `example.cpp` | Main simulation driver |
| `input2d` | Simulation parameters (grid, timestep, viscosity, etc.) |
| `Cylinder2d.py` | Generates the cylinder surface vertex file |
| `cylinder2d.vertex` | Pre-generated vertex file (used as fallback) |
| `CMakeLists.txt` | CMake build definition |
| `singularity/ibamr.def` | Container definition (Ubuntu 22.04 + autoibamr) |
| `singularity/build-container.sh` | Build the `.sif` container image |
| `singularity/run-IBAMR-torch.bash` | Run any command inside the container |
| `singularity/run-simulation.slurm` | SLURM job script |
| `setup_run.py` | Create run folder and submit to SLURM |
