#!/usr/bin/env python3
"""
setup_sweep.py — Build a parameter-sweep of IBAMR 2D rotating cylinder runs.

You pick any parameter(s) that appear in input2d and give each a
min:max:step.  The script takes the cartesian product of all sweep axes
and creates one self-contained run subfolder per combination, each with
its own modified input2d.

Run from anywhere:

    # Sweep Reynolds number 50 -> 200 in steps of 50 (4 runs)
    python3 setup_sweep.py --sweep Re:50:200:50

    # 2-D sweep: Re x oscillation frequency  (4 x 4 = 16 runs)
    python3 setup_sweep.py --sweep Re:50:200:50 --sweep frequency:0.2:0.5:0.1

    # Preview combinations without writing anything
    python3 setup_sweep.py --sweep MU:0.005:0.02:0.005 --dry-run

    # Create the folders AND submit each one to SLURM
    python3 setup_sweep.py --sweep Re:50:200:50 --submit

Folder layout produced:

    YYYY-MM-DD_HH-MM-SS_sweep/
        sweep_manifest.json        <- records axes, ranges, every combo
        archive/                   <- one shared snapshot of all source files
        <param-value__param-value>/    one folder per combination, e.g.
            input2d                <- copy of input2d with this combo applied
            cylinder2d.vertex      <- cylinder surface mesh
            viz_cylinder2d/        <- (empty) sim visualization output
            restart_IB2d/          <- (empty) restart checkpoints
            cylinder_dump/         <- (empty) constraint IB force/velocity output
            Dump--Cylinder/        <- (empty) constraint IB dump output
        ...

Each parameter is matched in input2d as a line of the form

    NAME = value      // optional comment

and only the value is rewritten (comments are preserved).  Any scalar
parameter defined that way can be swept (Re, MU, RHO, R, Nx, Ny,
END_TIME, DT_MAX, frequency, U_infinity, ...).
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

# -------------------------------------------------------------------------
# Paths / constants (kept consistent with setup_run.py)
# -------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parent
RUNS_DIR    = PROJECT_DIR

SOURCE_FILES = [
    "example.cpp",
    "CartGridBodyForce.cpp",
    "CartGridBodyForce.h",
    "ForceProjector.cpp",
    "ForceProjector.h",
    "OscillatingCylinderKinematics.cpp",
    "OscillatingCylinderKinematics.h",
    "CMakeLists.txt",
    "Cylinder2d.py",
    "input2d",
    "singularity/ibamr.def",
    "singularity/build-container.sh",
    "singularity/run-IBAMR-torch.bash",
    "singularity/run-simulation.slurm",
    "setup_run.py",
    "setup_sweep.py",
]

SIM_OUTPUT_DIRS = [
    "viz_cylinder2d",
    "restart_IB2d",
    "cylinder_dump",
    "Dump--Cylinder",
]

# -------------------------------------------------------------------------
# Sweep-axis parsing and value generation
# -------------------------------------------------------------------------

def parse_sweep_spec(spec):
    """Parse a 'NAME:MIN:MAX:STEP' string into a sweep axis dict."""
    parts = spec.split(":")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            f"--sweep expects NAME:MIN:MAX:STEP, got '{spec}'"
        )
    name, lo_s, hi_s, step_s = parts
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError(f"empty parameter name in '{spec}'")
    try:
        lo, hi, step = float(lo_s), float(hi_s), float(step_s)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"MIN/MAX/STEP must be numbers in '{spec}'"
        )
    if step <= 0:
        raise argparse.ArgumentTypeError(f"STEP must be > 0 in '{spec}'")
    if hi < lo:
        raise argparse.ArgumentTypeError(f"MAX < MIN in '{spec}'")
    # Treat the axis as integer if min/max/step are all whole numbers.
    is_int = all(float(v).is_integer() for v in (lo, hi, step))
    return {"name": name, "min": lo, "max": hi, "step": step, "is_int": is_int}


def axis_values(axis):
    """Inclusive list of values for an axis, computed without float drift."""
    lo, hi, step = axis["min"], axis["max"], axis["step"]
    # Number of steps; small epsilon so an exact endpoint isn't dropped.
    n = int((hi - lo) / step + 1e-9)
    values = [lo + i * step for i in range(n + 1)]
    # Guard against float overshoot just past hi.
    values = [v for v in values if v <= hi + 1e-9 * max(1.0, abs(hi))]
    if axis["is_int"]:
        return [int(round(v)) for v in values]
    return [round(v, 12) for v in values]


def fmt_value(v):
    """Format a value for the input file / folder name (trim trailing zeros)."""
    if isinstance(v, int):
        return str(v)
    s = f"{v:.10f}".rstrip("0").rstrip(".")
    return s if s else "0"


def cartesian(axes):
    """Yield combos as lists of (name, value) preserving axis order."""
    combos = [[]]
    for axis in axes:
        combos = [c + [(axis["name"], val)] for c in combos for val in axis_values(axis)]
    return combos


def combo_folder_name(combo):
    """Filesystem-safe folder name like 'Re-100__frequency-0.3'."""
    return "__".join(f"{name}-{fmt_value(val)}" for name, val in combo)


# -------------------------------------------------------------------------
# input2d rewriting
# -------------------------------------------------------------------------

def apply_params(text, combo):
    """Return input2d text with each swept parameter's value rewritten.

    Matches lines of the form `NAME = value   // comment`, rewriting only
    the value and preserving any trailing comment.  Raises if a parameter
    is never found so silent no-op sweeps can't slip through.
    """
    import re

    out = text
    for name, val in combo:
        # NAME, then optional spaces, '=', spaces, the value, optional comment.
        pattern = re.compile(
            rf"^(?P<pre>\s*{re.escape(name)}\s*=\s*)"
            rf"(?P<val>[^/\n]+?)"
            rf"(?P<post>\s*(?://.*)?)$",
            re.MULTILINE,
        )
        new_text, count = pattern.subn(
            lambda m: f"{m.group('pre')}{fmt_value(val)}{m.group('post')}", out
        )
        if count == 0:
            raise ValueError(
                f"parameter '{name}' not found as a 'NAME = value' line in input2d"
            )
        out = new_text
    return out


# -------------------------------------------------------------------------
# Per-combo folder construction
# -------------------------------------------------------------------------

def build_combo_dir(sweep_dir, combo, input2d_text, vertex_src):
    """Create one run subfolder for a single parameter combination."""
    name = combo_folder_name(combo)
    cdir = sweep_dir / name
    cdir.mkdir()

    for d in SIM_OUTPUT_DIRS:
        (cdir / d).mkdir()

    (cdir / "input2d").write_text(apply_params(input2d_text, combo))

    if vertex_src is not None and vertex_src.exists():
        shutil.copy2(vertex_src, cdir / "cylinder2d.vertex")

    return cdir


def submit_combo(cdir, executable, sif, slurm_script):
    """sbatch a single combo folder; return (ok, message)."""
    result = subprocess.run(
        [
            "sbatch",
            f"--chdir={cdir}",
            f"--export=ALL,IBAMR_PROJECT_DIR={PROJECT_DIR},IBAMR_SIF={sif},IBAMR_EXECUTABLE={executable}",
            str(slurm_script),
            "input2d",
        ],
        cwd=str(cdir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, result.stderr.strip()
    info = result.stdout.strip()
    return True, info.split()[-1] if info else "?"


def submit_runs(sweep_dir, run_dirs):
    """Submit every run folder in an (already-created) sweep to SLURM.

    run_dirs is a list of (folder_name, Path).  Job ids are written back
    into the sweep's sweep_manifest.json.  Returns the number submitted.
    """
    slurm_script = PROJECT_DIR / "singularity" / "run-simulation.slurm"
    executable   = PROJECT_DIR / "build" / "main2d"
    sif          = PROJECT_DIR / "singularity" / "ibamr.sif"

    for label, path in [("executable", executable), ("container", sif), ("slurm script", slurm_script)]:
        if not path.exists():
            print(f"  ERROR: {label} not found: {path}")
            if label == "executable":
                print("         Build first: bash singularity/run-IBAMR-torch.bash make-sim")
            sys.exit(1)

    print(f"  Submitting {len(run_dirs)} SLURM jobs ...")
    submitted = {}
    for name, cdir in run_dirs:
        if not (cdir / "input2d").exists():
            print(f"        {name}  ->  SKIPPED: no input2d in folder")
            continue
        ok, msg = submit_combo(cdir, executable, sif, slurm_script)
        if ok:
            submitted[name] = msg
            print(f"        {name}  ->  job {msg}")
        else:
            print(f"        {name}  ->  FAILED: {msg}")

    # Record job ids back into the manifest if one exists.
    manifest_path = sweep_dir / "sweep_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for run in manifest.get("runs", []):
            run["job_id"] = submitted.get(run["folder"])
        manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f"""
=== Sweep submitted ===
  Sweep folder : {sweep_dir}
  Jobs queued  : {len(submitted)}/{len(run_dirs)}

  Monitor : squeue -u $USER
  Cancel  : scancel <jobid>   (job ids in sweep_manifest.json)
""")
    return len(submitted)


def submit_existing(sweep_dir):
    """Load an already-created sweep folder and submit all its runs."""
    sweep_dir = Path(sweep_dir).resolve()
    manifest_path = sweep_dir / "sweep_manifest.json"
    if not manifest_path.exists():
        print(f"  ERROR: no sweep_manifest.json in {sweep_dir}")
        print("         Is this a sweep folder created by setup_sweep.py?")
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text())
    runs = manifest.get("runs", [])
    if not runs:
        print(f"  ERROR: sweep_manifest.json lists no runs")
        sys.exit(1)

    already = [r["folder"] for r in runs if r.get("job_id")]
    if already:
        print(f"  WARNING: {len(already)} run(s) already have a job_id recorded "
              f"(re-submitting will queue duplicates):")
        for name in already:
            print(f"           {name}")
        print()

    run_dirs = [(r["folder"], sweep_dir / r["folder"]) for r in runs]
    print(f"=== Submitting existing sweep ===")
    print(f"  Sweep folder : {sweep_dir}")
    print(f"  Runs         : {len(run_dirs)}\n")
    submit_runs(sweep_dir, run_dirs)


# -------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Create a parameter sweep of IBAMR rotating-cylinder runs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--sweep",
        dest="sweeps",
        action="append",
        metavar="NAME:MIN:MAX:STEP",
        type=parse_sweep_spec,
        help="Parameter to sweep (repeatable). E.g. --sweep Re:50:200:50",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Also submit each combo to SLURM right after creating it.",
    )
    parser.add_argument(
        "--submit-dir",
        metavar="SWEEP_FOLDER",
        help="Submit an existing sweep folder (created by an earlier run). "
             "Does not create anything; just sbatches each run inside it.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the combinations that would be created and exit.",
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Mode: submit an already-created sweep folder, no creation.
    # ------------------------------------------------------------------
    if args.submit_dir:
        if args.sweeps:
            print("  ERROR: use either --sweep (to create) or --submit-dir "
                  "(to submit an existing sweep), not both.")
            sys.exit(1)
        submit_existing(args.submit_dir)
        return

    if not args.sweeps:
        parser.error("one of --sweep or --submit-dir is required")

    axes = args.sweeps
    combos = cartesian(axes)

    # ------------------------------------------------------------------
    # Summary / dry run
    # ------------------------------------------------------------------
    print("=== Parameter sweep ===")
    for a in axes:
        vals = ", ".join(fmt_value(v) for v in axis_values(a))
        print(f"  {a['name']:<14} [{fmt_value(a['min'])} .. {fmt_value(a['max'])} "
              f"step {fmt_value(a['step'])}]  ->  {{ {vals} }}")
    print(f"  Total combinations: {len(combos)}\n")

    if args.dry_run:
        for i, combo in enumerate(combos, 1):
            print(f"  [{i:>3}] {combo_folder_name(combo)}")
        print("\n(dry run — nothing written)")
        return

    input2d_src = PROJECT_DIR / "input2d"
    if not input2d_src.exists():
        print(f"  ERROR: input2d not found at {input2d_src}")
        sys.exit(1)
    input2d_text = input2d_src.read_text()

    # Validate every parameter resolves against input2d before writing anything.
    try:
        for combo in combos[:1]:
            apply_params(input2d_text, combo)
    except ValueError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Create sweep folder + shared source archive
    # ------------------------------------------------------------------
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    sweep_dir = RUNS_DIR / f"{timestamp}_sweep"
    sweep_dir.mkdir(parents=True)
    print(f"  Sweep directory: {sweep_dir}\n")

    archive_dir = sweep_dir / "archive"
    archive_dir.mkdir()
    missing = []
    for rel in SOURCE_FILES:
        src = PROJECT_DIR / rel
        if src.exists():
            shutil.copy2(src, archive_dir / src.name)
        else:
            missing.append(rel)
    if missing:
        print(f"  WARNING: missing source files (not archived): {missing}")
    print(f"  [1/3] Archived {len(SOURCE_FILES) - len(missing)} source files -> archive/")

    # Cylinder surface mesh: reuse the pre-generated vertex file (the file
    # IBAMR's IBStandardInitializer actually reads as 'cylinder2d.vertex').
    vertex_src = PROJECT_DIR / "cylinder2d.vertex"
    if not vertex_src.exists():
        print(f"  WARNING: {vertex_src.name} not found; combo folders will lack it")
        vertex_src = None

    # ------------------------------------------------------------------
    # Build one folder per combination
    # ------------------------------------------------------------------
    print(f"  [2/3] Creating {len(combos)} run folders ...")
    combo_dirs = []
    for combo in combos:
        cdir = build_combo_dir(sweep_dir, combo, input2d_text, vertex_src)
        combo_dirs.append((combo, cdir))
        print(f"        + {cdir.name}")

    manifest = {
        "created": timestamp,
        "project_dir": str(PROJECT_DIR),
        "axes": [
            {
                "name": a["name"],
                "min": a["min"],
                "max": a["max"],
                "step": a["step"],
                "values": axis_values(a),
            }
            for a in axes
        ],
        "num_combinations": len(combos),
        "runs": [
            {"folder": cdir.name, "params": {n: v for n, v in combo}}
            for combo, cdir in combo_dirs
        ],
    }
    (sweep_dir / "sweep_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"        wrote sweep_manifest.json")

    # ------------------------------------------------------------------
    # Optionally submit each combo to SLURM
    # ------------------------------------------------------------------
    if not args.submit:
        print(f"\n  [3/3] Setup only (no jobs submitted).")
        print(f"""
=== Sweep ready ===
  Sweep folder : {sweep_dir}
  Runs created : {len(combos)}

  Review the folders, then submit them all with:
      python3 setup_sweep.py --submit-dir {sweep_dir}

  Or submit a single run by hand:
      sbatch --chdir={sweep_dir}/<run-folder> \\
             --export=ALL,IBAMR_PROJECT_DIR={PROJECT_DIR},IBAMR_SIF={PROJECT_DIR}/singularity/ibamr.sif,IBAMR_EXECUTABLE={PROJECT_DIR}/build/main2d \\
             {PROJECT_DIR}/singularity/run-simulation.slurm input2d
""")
        return

    print(f"\n  [3/3] Submitting jobs ...")
    submit_runs(sweep_dir, [(cdir.name, cdir) for combo, cdir in combo_dirs])


if __name__ == "__main__":
    main()
