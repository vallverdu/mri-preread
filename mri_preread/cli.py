"""mri-preread command line.

  mri-preread extract <dicom-folder> <study>   DICOM -> <study>/nifti, series.json, study.json, roles.json
  mri-preread analyze <study>                  skull strip, registration, heterogeneity maps (~1-2 min)
  mri-preread build   <study>                  <study>/brain_viewer.html
  mri-preread all     <dicom-folder> <study>   the three steps above
  mri-preread import  <study> --flair F --dwi F ...   study from NIfTI files instead of DICOM
  mri-preread serve   <study>                  MCP server (stdio) + live viewer on http://127.0.0.1:8765

<study> can be omitted when $MRI_PREREAD_STUDY is set.
"""
import argparse
import os

from .study import ROLES, Study, resolve


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mri-preread", description="Brain MRI 3D viewer, heterogeneity maps and LLM pre-read.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("extract", "all"):
        p = sub.add_parser(name)
        p.add_argument("dicom", help="folder with the DICOM export (searched recursively)")
        p.add_argument("study", help="study folder to create or update")
        p.add_argument("--png", action="store_true", help="also write every image as PNG")
    p = sub.add_parser("import", help="create a study from NIfTI files")
    p.add_argument("study")
    for r in ROLES: p.add_argument(f"--{r}", metavar="NIFTI")
    for name in ("analyze", "build", "serve"):
        parser = sub.add_parser(name)
        parser.add_argument("study", nargs="?")
        if name == "build":
            parser.add_argument("--medgemma-report", help="attach a completed aligned-slice JSON report after verifying its image hashes")
    from .medgemma import configure_parser
    configure_parser(sub)
    from .worklist import configure_parser as configure_worklist
    configure_worklist(sub)
    a = ap.parse_args(argv)

    if a.cmd == "worklist":
        from .worklist import main as worklist_main
        worklist_main(a)
        return
    if a.cmd == "medgemma":
        from .medgemma import main as medgemma_main
        medgemma_main(a)
        return
    if a.cmd == "import":
        from . import extract
        files = {r: getattr(a, r) for r in ROLES if getattr(a, r)}
        if not files: raise SystemExit("give at least one of --" + " --".join(ROLES))
        os.makedirs(a.study, exist_ok=True); extract.from_nifti(files, Study(a.study)); return
    if a.cmd in ("extract", "all"):
        from . import extract
        os.makedirs(a.study, exist_ok=True); study = Study(a.study)
        extract.run(a.dicom, study, png=a.png)
        if a.cmd == "extract": return
    else:
        study = resolve(a.study)
    if a.cmd in ("analyze", "all"):
        from . import analyze
        analyze.run(study)
    if a.cmd in ("build", "all"):
        from . import build_viewer
        build_viewer.run(study, medgemma_report=getattr(a, "medgemma_report", None))
    if a.cmd == "serve":
        from . import mcp_server
        mcp_server.main(study)


if __name__ == "__main__":
    main()
