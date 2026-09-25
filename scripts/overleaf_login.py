"""Login to Overleaf via Playwright, extract cookies, push paper via API."""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv(override=True)

OVERLEAF_EMAIL = os.getenv("OVERLEAF_EMAIL", "")
OVERLEAF_PASS = os.getenv("OVERLEAF_PASSWORD", "")
PROJECT_ID = "6a3d486be33b9fd1b48c28a8"
PAPER_DIR = Path(__file__).parent.parent / "publish" / "surf_revised_new"

if not OVERLEAF_EMAIL or not OVERLEAF_PASS:
    print("ERROR: Set OVERLEAF_EMAIL and OVERLEAF_PASSWORD in .env")
    sys.exit(1)

def login_overleaf():
    """Login to Overleaf via headless browser, return cookies + csrf token."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()

        print("Navigating to Overleaf login...")
        page.goto("https://www.overleaf.com/login", wait_until="networkidle", timeout=30000)

        # Fill login form
        page.fill('input[name="email"]', OVERLEAF_EMAIL)
        page.fill('input[name="password"]', OVERLEAF_PASS)
        page.click('button[type="submit"]')

        # Wait for redirect after login
        page.wait_for_url("https://www.overleaf.com/project", timeout=30000)
        print("Login successful!")

        # Get cookies
        cookies = ctx.cookies()
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

        # Get CSRF token from page
        csrf = page.evaluate("() => document.querySelector('meta[name=\"ol-csrfToken\"]')?.content || ''")
        if not csrf:
            csrf = page.evaluate("() => document.querySelector('meta[name=\"csrf-token\"]')?.content || ''")

        browser.close()
        return cookie_str, csrf

def upload_file(session, csrf, project_id, filepath, target_path):
    """Upload a file to Overleaf project via web API."""
    import requests

    headers = {
        "Cookie": session,
        "X-CSRF-Token": csrf,
        "Origin": "https://www.overleaf.com",
        "Referer": f"https://www.overleaf.com/project/{project_id}",
    }

    # Read file
    with open(filepath, "rb") as f:
        content = f.read()

    # Overleaf upload endpoint
    files = {"file": (Path(filepath).name, content, "application/octet-stream")}
    data = {"folder": str(Path(target_path).parent)}

    url = f"https://www.overleaf.com/project/{project_id}/upload"
    resp = requests.post(url, headers=headers, files=files, data=data, timeout=30)
    return resp.status_code == 200

def push_paper(session, csrf):
    """Push all paper files to Overleaf."""
    files_to_upload = [
        ("paper_main.tex", ""),
        ("sec_abstract.tex", ""),
        ("sec_intro.tex", ""),
        ("sec_related.tex", ""),
        ("sec_methodology.tex", ""),
        ("sec_results.tex", ""),
        ("sec_discussion.tex", ""),
        ("sec_conclusion.tex", ""),
        ("sec_bibliography.tex", ""),
        ("surf_references.bib", ""),
        ("figures/design_diagram.pdf", "figures"),
        ("figures/doseresponse.pdf", "figures"),
        ("figures/pipeline.pdf", "figures"),
        ("figures/regime.pdf", "figures"),
    ]

    success = 0
    for fname, folder in files_to_upload:
        fpath = PAPER_DIR / fname
        if not fpath.exists():
            print(f"  SKIP {fname}: not found")
            continue
        ok = upload_file(session, csrf, PROJECT_ID, fpath, f"{folder}/{Path(fname).name}" if folder else fname)
        status = "OK" if ok else "FAIL"
        if ok:
            success += 1
        print(f"  {fname}: {status}")

    print(f"\n{success}/{len(files_to_upload)} uploaded")

if __name__ == "__main__":
    print("Logging into Overleaf...")
    session_cookie, csrf_token = login_overleaf()
    print(f"Got session cookie ({len(session_cookie)} chars)")
    print(f"Got CSRF: {csrf_token[:20] if csrf_token else 'NONE'}...")

    if csrf_token:
        print("\nUploading paper files...")
        push_paper(session_cookie, csrf_token)
    else:
        print("ERROR: Could not get CSRF token")
