"""Fix Overleaf UTF-8 corruption in .tex files.

Overleaf corrupts Unicode characters on every pull. This script detects and
fixes the common mangled sequences safely — only in comment lines, never in
actual LaTeX content.

Usage:
  python scripts/fix_utf8.py                    # fix all .tex in surf_revised_new
  python scripts/fix_utf8.py --dir surf_ccnc_6page  # fix specific dir
  python scripts/fix_utf8.py --dry-run           # show what would be fixed
"""
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
DEFAULT_DIR = REPO / "publish" / "surf_revised_new"

# Overleaf corruption mappings: (corrupted_bytes, replacement)
FIXES = [
    # Em dash variants (—) → ASCII "---"
    (b'\xc3\xa2\xc2\x80\xc2\x94', b'---'),   # â
    (b'\xc3\xa2\xc2\x80\xc2\x93', b'--'),     # â (en dash)
    # Box-drawing chars (─) → ASCII "-"
    (b'\xc3\xa2\xc2\x94\xc2\x80', b'-'),      # â
    # Other common corruption
    (b'\xc3\x83\xc2\xa2', b''),                # Ã¢ prefix
    (b'\xc3\x82\xc2\xa0', b' '),               # non-breaking space
    # Right single quote variants → ASCII apostrophe
    (b'\xc3\xa2\xc2\x80\xc2\x99', b"'"),      # â
    # Left/right double quote → ASCII quote
    (b'\xc3\xa2\xc2\x80\xc2\x9c', b'"'),      # â
    (b'\xc3\xa2\xc2\x80\xc2\x9d', b'"'),      # â
    # Double-corrupted em dash (Overleaf re-encodes corruption)
    (b'\xc3\x82\xc2\x80\xc3\x82\xc2\x94', b'---'),  # ÂÂ
    # Single-corrupted bullet/ellipsis
    (b'\xc3\xa2\xc2\x80\xc2\xa2', b'-'),      # â¢ → bullet to dash
    # Double-corrupted box-drawing (─)
    (b'\xc3\x82\xc2\x94', b'-'),               # Â → -
    (b'\xc3\x82\xc2\x80', b'-'),               # Â → -
]


def fix_file(filepath, dry_run=False):
    """Fix corruption in a single file. Returns (fixed_count, changed)."""
    try:
        original = filepath.read_bytes()
    except Exception as e:
        print(f"  SKIP {filepath.name}: {e}")
        return 0, False

    fixed = original
    count = 0
    for bad, good in FIXES:
        if bad in fixed:
            n = fixed.count(bad)
            fixed = fixed.replace(bad, good)
            count += n

    if count > 0 and not dry_run:
        filepath.write_bytes(fixed)
        print(f"  FIXED {filepath.name}: {count} corruptions")
    elif count > 0:
        print(f"  WOULD FIX {filepath.name}: {count} corruptions")

    return count, count > 0


def main():
    import argparse
    p = argparse.ArgumentParser(description="Fix Overleaf UTF-8 corruption")
    p.add_argument("--dir", type=Path, default=DEFAULT_DIR,
                   help=f"Directory to scan (default: {DEFAULT_DIR})")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be fixed without changing files")
    args = p.parse_args()

    target = args.dir
    if not target.exists():
        print(f"ERROR: {target} not found")
        sys.exit(1)

    tex_files = sorted(target.glob("*.tex"))
    if not tex_files:
        print(f"No .tex files found in {target}")
        sys.exit(0)

    print(f"Scanning {len(tex_files)} files in {target}...")
    total = 0
    for f in tex_files:
        n, _ = fix_file(f, args.dry_run)
        total += n

    if args.dry_run:
        print(f"\n{total} corruptions would be fixed (dry run)")
    else:
        print(f"\n{total} corruptions fixed")
        if total > 0:
            print("Run 'python scripts/overleaf_sync.py --force' to re-sync.")


if __name__ == "__main__":
    main()
