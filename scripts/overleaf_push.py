"""Login to Overleaf via Playwright, push SURF paper via pyoverleaf."""
import os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
load_dotenv(override=True)

OVERLEAF_EMAIL = os.getenv("OVERLEAF_EMAIL", "")
OVERLEAF_PASS = os.getenv("OVERLEAF_PASSWORD", "")
PROJECT_ID = os.getenv("OVERLEAF_PROJECT_ID", "6a3d486be33b9fd1b48c28a8")
PAPER_DIR = Path(__file__).parent.parent / "publish" / "surf_revised_new"

if not OVERLEAF_EMAIL or not OVERLEAF_PASS:
    print("ERROR: Set OVERLEAF_EMAIL and OVERLEAF_PASSWORD in .env")
    sys.exit(1)

def login_overleaf():
    """Login to Overleaf via headless browser, return pyoverleaf-compatible cookies."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()

        print("Navigating to Overleaf login...")
        page.goto("https://www.overleaf.com/login", wait_until="networkidle", timeout=30000)

        # Click "Log in with Email" if needed
        try:
            page.click('text=Log in with Email', timeout=3000)
        except:
            pass  # May already be on email form

        page.fill('input[name="email"]', OVERLEAF_EMAIL)
        page.fill('input[name="password"]', OVERLEAF_PASS)
        page.click('button[type="submit"]')

        # Wait for redirect
        page.wait_for_url("https://www.overleaf.com/project**", timeout=30000)
        print("Login successful!")

        # Get cookies as dict (pyoverleaf-compatible format)
        cookies = {c['name']: c['value'] for c in ctx.cookies()}
        browser.close()
        return cookies

def push_paper(cookies):
    """Push all paper files to Overleaf using pyoverleaf."""
    import pyoverleaf

    api = pyoverleaf.Api()
    api.login_from_cookies(cookies)

    # Verify access
    try:
        project = api.get_project(PROJECT_ID)
        print(f"Connected to project: {project.get('name', PROJECT_ID)}")
    except Exception as e:
        print(f"ERROR accessing project: {e}")
        return

    pio = pyoverleaf.ProjectIO(api, PROJECT_ID)

    files_to_upload = [
        "paper_main.tex", "sec_abstract.tex", "sec_intro.tex", "sec_related.tex",
        "sec_methodology.tex", "sec_results.tex", "sec_discussion.tex", "sec_conclusion.tex",
        "sec_bibliography.tex", "surf_references.bib",
    ]
    figures = ["figures/design_diagram.pdf", "figures/doseresponse.pdf", "figures/pipeline.pdf", "figures/regime.pdf"]

    success = 0
    total = len(files_to_upload) + len(figures)

    # Upload tex/bib files to root
    for fname in files_to_upload:
        fpath = PAPER_DIR / fname
        if not fpath.exists():
            print(f"  SKIP {fname}")
            continue
        try:
            pio.put_file(fname, fpath.read_text())
            print(f"  OK  {fname}")
            success += 1
        except Exception as e:
            print(f"  FAIL {fname}: {e}")

    # Upload figures to figures/ folder
    for fname in figures:
        fpath = PAPER_DIR / fname
        base = Path(fname).name
        if not fpath.exists():
            print(f"  SKIP {fname}")
            continue
        try:
            pio.put_file(f"figures/{base}", fpath.read_bytes())
            print(f"  OK  {fname}")
            success += 1
        except Exception as e:
            print(f"  FAIL {fname}: {e}")

    print(f"\n{success}/{total} files uploaded")
    print(f"Open: https://www.overleaf.com/project/{PROJECT_ID}")

if __name__ == "__main__":
    print("Logging into Overleaf via Playwright...")
    cookies = login_overleaf()
    print(f"Got {len(cookies)} cookies")

    print("\nPushing paper files via pyoverleaf...")
    push_paper(cookies)
