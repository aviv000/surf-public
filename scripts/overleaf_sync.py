"""Sync paper files to Overleaf — push/pull with hash-based change detection.

Usage:
  python overleaf_sync.py                # push changed files
  python overleaf_sync.py --pull         # pull Revital's review (overwrites!)
  python overleaf_sync.py --safe-pull    # pull to temp, show diffs (safe)
  python overleaf_sync.py --safe-pull --full  # safe-pull with full diffs
  python overleaf_sync.py --view-diff    # re-show last safe-pull diffs
  python overleaf_sync.py --view-diff sec_results  # show diff for one file
  python overleaf_sync.py --dry-run      # preview push changes
  python overleaf_sync.py --force        # upload all, ignore hashes

Config in .env:
  OVERLEAF_SESSION_COOKIE  — from browser DevTools > Cookies > overleaf_session2
  OVERLEAF_PROJECT_ID      — from Overleaf project URL
  OVERLEAF_PAPER_DIR       — (optional) paper directory path
"""
import hashlib, json, os, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(override=True)

import pyoverleaf

PROJECT_ID = os.getenv("OVERLEAF_PROJECT_ID", "")
SESSION = os.getenv("OVERLEAF_SESSION_COOKIE", "")
PAPER_DIR = Path(os.getenv("OVERLEAF_PAPER_DIR",
    str(Path(__file__).parent.parent / "publish" / "surf_revised_new")))
CCNC_PAPER_DIR = Path(os.getenv("OVERLEAF_CCNC_PAPER_DIR",
    str(Path(__file__).parent.parent / "publish" / "surf_ccnc_6page")))
CCNC_PROJECT_ID = os.getenv("OVERLEAF_CCNC_PROJECT_ID", "6a4051e337ccd5df02b5ddce")
HASH_FILE = Path(__file__).parent.parent / "outputs" / (
    f".overleaf_hashes_{PROJECT_ID[:8]}.json")

CCNC_FILES = {
    "paper_main.tex": "", "sec_abstract.tex": "", "sec_intro.tex": "",
    "sec_related.tex": "", "sec_methodology.tex": "", "sec_results.tex": "",
    "sec_discussion.tex": "", "sec_conclusion.tex": "", "sec_bibliography.tex": "",
    "Experimantal.tex": "",
    "references.bib": "",
    "figures/design_diagram.pdf": "figures", "figures/wordcount_curves.pdf": "figures",
    "figures/pipeline.pdf": "figures", "figures/pipeline_eval.pdf": "figures",
    "figures/generation1.pdf": "figures", "figures/evaluation1.pdf": "figures",
    "figures/regime.pdf": "figures",
}
# TKG paper (default project since 2026-09-11). Split into per-section files
# (CCNC convention) on 2026-09-11; the old single main.tex is pruned remotely.
TKG_FILES = {
    "main.tex": "",
    "gipf_proposal.tex": "",
    "hit_research_proposal.tex": "",
    "hit_research_proposal.md": "",
    "hit_research_proposal_gemini.md": "",
    "sec_abstract.tex": "",
    "sec_intro.tex": "",
    "sec_related.tex": "",
    "sec_system.tex": "",
    "sec_results.tex": "",
    "sec_discussion.tex": "",
    "sec_conclusion.tex": "",
    "sec_bibliography.tex": "",
    "references.bib": "",
}
FILES = TKG_FILES


def compute_hash(filepath): return hashlib.sha256(filepath.read_bytes()).hexdigest()
def load_hashes(): return json.loads(HASH_FILE.read_text()) if HASH_FILE.exists() else {}
def save_hashes(h): HASH_FILE.parent.mkdir(parents=True, exist_ok=True); HASH_FILE.write_text(json.dumps(h, indent=2))


def connect():
    api = pyoverleaf.Api()
    api.login_from_cookies({"overleaf_session2": SESSION})
    return api


def get_structure(api):
    f = api.project_get_files(PROJECT_ID).__dict__
    figs = next((c.__dict__["id"] for c in f.get("children", [])
                 if c.__dict__.get("name") == "figures"), None)
    return f["id"], figs


def pull(api):
    """Download changed files from Overleaf."""
    prev = load_hashes()
    pulled = 0

    def _walk(folder, prefix=""):
        nonlocal pulled
        for c in folder.__dict__.get("children", []):
            cd = c.__dict__
            name, ftype, cid = cd.get("name"), cd.get("type"), cd.get("id")
            if ftype == "folder":
                _walk(c, f"{prefix}{name}/")
            else:
                rel, local = f"{prefix}{name}", PAPER_DIR / f"{prefix}{name}"
                content = None
                if ftype == "doc":
                    t = api._pull_doc_project_file_content(PROJECT_ID, cid)
                    content = t.encode() if t else None
                elif ftype == "file":
                    content = api.project_download_file(PROJECT_ID, c)
                if not content: continue
                h = hashlib.sha256(content).hexdigest()
                if rel in prev and prev[rel] == h: continue
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(content)
                prev[rel] = h; pulled += 1
                print(f"  PULLED {rel}")

    _walk(api.project_get_files(PROJECT_ID))
    save_hashes(prev)
    print(f"\n{pulled} files pulled")


LAST_PULL_FILE = HASH_FILE.parent / ".last_safe_pull_path"


def safe_pull(api, full_diff=False):
    """Pull to temp dir, show diffs. Does NOT overwrite local files."""
    import tempfile, subprocess
    tmp = Path(tempfile.mkdtemp(prefix="overleaf_pull_"))
    LAST_PULL_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_PULL_FILE.write_text(str(tmp))

    global PAPER_DIR
    orig = PAPER_DIR
    PAPER_DIR = tmp
    try: pull(api)
    finally: PAPER_DIR = orig

    diffs = 0
    truncate_at = None if full_diff else 1500
    for f in sorted(tmp.rglob("*")):
        rel = f.relative_to(tmp)
        local = orig / str(rel)
        if f.is_dir(): continue
        if not local.exists():
            print(f"  NEW: {rel}"); diffs += 1
        elif f.read_bytes() != local.read_bytes():
            print(f"\n{'='*60}\n  DIFF: {rel}\n{'='*60}")
            try:
                r = subprocess.run(["diff", "-u", str(local), str(f)],
                                   capture_output=True, text=True, timeout=10)
                out = r.stdout if r.stdout else "(binary file)"
                if truncate_at and len(out) > truncate_at:
                    out = out[:truncate_at] + f"\n... [truncated at {truncate_at} chars, {len(r.stdout)} total]"
                print(out)
            except Exception as e: print(f"(diff failed: {e})")
            diffs += 1
    print(f"\n{diffs} changes in {tmp}")
    print("Full diffs: --view-diff    Apply: --pull")


def view_diff(path_filter=None):
    """Re-examine last safe-pull diffs without truncation."""
    import subprocess
    if not LAST_PULL_FILE.exists():
        print("No safe-pull data. Run --safe-pull first.")
        return

    tmp = Path(LAST_PULL_FILE.read_text().strip())
    if not tmp.exists():
        print(f"Temp dir gone: {tmp}\nRun --safe-pull again.")
        return

    orig = PAPER_DIR
    found = 0
    for f in sorted(tmp.rglob("*")):
        rel = f.relative_to(tmp)
        if f.is_dir(): continue
        if path_filter and path_filter not in str(rel): continue
        local = orig / str(rel)
        if not local.exists():
            print(f"  NEW: {rel}")
        elif f.read_bytes() != local.read_bytes():
            print(f"\n{'='*60}\n  DIFF: {rel}\n{'='*60}")
            try:
                r = subprocess.run(["diff", "-u", str(local), str(f)],
                                   capture_output=True, text=True, timeout=10)
                print(r.stdout if r.stdout else "(binary file)")
            except Exception as e: print(f"(diff failed: {e})")
        else:
            if path_filter: print(f"  (unchanged: {rel})")
        found += 1

    if path_filter and found == 0:
        print(f"No file matching '{path_filter}' in last safe-pull.")
    print(f"\nTemp: {tmp}")


def push(api, dry_run=False, force=False):
    """Upload changed local files to Overleaf."""
    root, figs = get_structure(api)
    if figs is None:
        api.project_create_folder(PROJECT_ID, root, "figures")
        root, figs = get_structure(api)

    prev = load_hashes()
    current = {}; to_upload = []; skipped = 0

    for rel, folder in FILES.items():
        lp = PAPER_DIR / rel
        if not lp.exists(): print(f"  MISSING {rel}"); continue
        h = compute_hash(lp); current[rel] = h
        if not force and rel in prev and prev[rel] == h: skipped += 1; continue
        target = figs if folder == "figures" else root
        to_upload.append((rel, lp, target, Path(rel).name))

    print(f"Changed/new: {len(to_upload)}, unchanged: {skipped}")
    if dry_run:
        for rel, *_ in to_upload: print(f"  WOULD UPLOAD: {rel}")
        return

    ok = 0
    for rel, lp, fid, fn in to_upload:
        try:
            api.project_upload_file(PROJECT_ID, fid, fn, lp.read_bytes())
            print(f"  OK  {rel}"); ok += 1
        except Exception as e:
            print(f"  FAIL {rel}: {e}")
            current[rel] = prev.get(rel, "")

    save_hashes(current)
    print(f"\n{ok}/{len(to_upload)} uploaded, {skipped} skipped")
    if ok: print(f"https://www.overleaf.com/project/{PROJECT_ID}")


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--pull", action="store_true")
    p.add_argument("--safe-pull", action="store_true", help="Pull to temp, show diffs (safe)")
    p.add_argument("--full", action="store_true", help="Show full diffs (no truncation, use with --safe-pull)")
    p.add_argument("--view-diff", nargs="?", const="", metavar="FILE",
                   help="Re-show last safe-pull diffs, optionally filtered by FILE")
    p.add_argument("--ccnc", action="store_true", help="Target CCNC 6-page project instead of main")
    p.add_argument("--push", action="store_true")
    p.add_argument("--prune", action="store_true",
                   help="Delete remote files not in the active FILES mapping "
                        "(e.g. superseded single-file drafts)")
    args = p.parse_args()

    do_push = args.push or (not args.pull and not args.safe_pull and not args.view_diff)
    do_pull = args.pull
    do_safe_pull = args.safe_pull
    do_view = args.view_diff is not None

    global PROJECT_ID, PAPER_DIR, FILES
    if args.ccnc:
        PROJECT_ID = CCNC_PROJECT_ID
        PAPER_DIR = CCNC_PAPER_DIR
        FILES = CCNC_FILES
    else:
        FILES = TKG_FILES

    if not SESSION or not PROJECT_ID:
        print("ERROR: Set OVERLEAF_SESSION_COOKIE and OVERLEAF_PROJECT_ID in .env")
        sys.exit(1)

    if do_view:
        view_diff(args.view_diff if args.view_diff != "" else None)
        return

    print(f"Project: {PROJECT_ID}")
    api = connect()

    if args.prune:
        def _prune_walk(folder, prefix=""):
            for c in folder.__dict__.get("children", []):
                cd = c.__dict__
                name = cd.get("name")
                if "children" in cd:  # folder
                    _prune_walk(c, f"{prefix}{name}/")
                else:
                    rel = f"{prefix}{name}"
                    if rel not in FILES:
                        print(f"  PRUNE {rel}")
                        api.project_delete_entity(PROJECT_ID, c)
        _prune_walk(api.project_get_files(PROJECT_ID))
        print("prune complete")

    if do_safe_pull: safe_pull(api, full_diff=args.full)
    elif do_pull: pull(api)
    if do_push: push(api, args.dry_run, args.force)


if __name__ == "__main__":
    main()
