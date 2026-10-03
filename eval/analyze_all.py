"""Analyze and build every case_* study under a benchmark folder, in parallel.
  python eval/analyze_all.py data/benchmark [--jobs 4]"""
import argparse
import glob
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor


def run(study):
    with open(os.path.join(study, "analyze.log"), "w") as log:
        for cmd in ("analyze", "build"):
            r = subprocess.run([sys.executable, "-m", "mri_preread", cmd, study], stdout=log, stderr=subprocess.STDOUT)
            if r.returncode: return f"FAILED {cmd} {study}"
    return f"done {study}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("root"); ap.add_argument("--jobs", type=int, default=4); a = ap.parse_args()
    with ThreadPoolExecutor(a.jobs) as ex:
        for msg in ex.map(run, sorted(glob.glob(os.path.join(a.root, "case_*")))): print(msg, flush=True)
