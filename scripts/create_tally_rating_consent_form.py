"""Create TKG rating-variant consent form on Tally.so via API.

This is the second (transparent) variant of the consent form:
participants openly rate example phishing emails on a 1-7 persuasion
scale instead of receiving phishing emails (Option B in the IRB).

Live form: https://tally.so/r/VL7x8J

Same block-type rules as create_tally_consent_form.py.
"""

import os, sys, uuid, requests
from dotenv import load_dotenv

load_dotenv(override=True)
API_KEY = os.getenv("TALLY_API_KEY")
if not API_KEY:
    print("ERROR: TALLY_API_KEY not found in .env"); sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

def U(): return str(uuid.uuid4())

def block(typ, group_type=None, html=None, title=None):
    b = {"uuid": U(), "type": typ, "groupUuid": U(),
         "groupType": group_type or typ, "payload": {}}
    if html:  b["payload"]["html"] = html
    if title: b["payload"]["title"] = title
    return b

# ---------------------------------------------------------------------------
blocks = []

# === Page 1: Study Information ===
blocks.append(block("FORM_TITLE",
    html="<h1>Informed Consent: Phishing Email Rating Study</h1>",
    title="Informed Consent: Phishing Email Rating Study"))

STUDY_INFO = """
<p><strong>Study Title:</strong> Quantifying Personalized Phishing Risk: From Generic Baselines to Temporal Knowledge Graphs</p>
<p><strong>Principal Investigator:</strong> Dr. Revital Marbel, Holon Institute of Technology (HIT), School of Computer Science</p>
<p><strong>Co-Investigators:</strong> Aviv Elbaz (HIT), Dr. Harel Berger (Ariel University)</p>
<br>
<p><strong>What this study is about:</strong> We are measuring how persuasive AI-generated phishing emails can be when personalized using publicly available information (academic publications, public profiles, public social media posts). In this stage of the study, you will be shown a set of example phishing emails and asked to rate how persuasive each one is.</p>
<br>
<p><strong>What you will do:</strong> You will review a set of sample emails (both generic and personalized) and rate each one on a persuasion scale of 1 to 7. The task is fully transparent: you will know you are evaluating phishing emails. No phishing emails will be sent to you. The task takes about 15 to 20 minutes and is completed online in a single session.</p>
<br>
<p><strong>Your data:</strong> We collect your ratings and basic professional details (name, email, institution). Ratings are stored separately from identifying information and are reported only in aggregated, anonymous form. You may request deletion of all your data at any time.</p>
<br>
<p><strong>Your rights:</strong> Participation is entirely voluntary. You may withdraw at any time and request immediate deletion of all your data, with no consequences to your employment, academic standing, or student status. You may skip any email you prefer not to rate.</p>
<br>
<p><strong>Risk:</strong> Minimal. The emails you will rate are simulated phishing examples generated from publicly available information. You may experience mild discomfort from seeing realistic personalized phishing content.</p>
<br>
<p><strong>Contact:</strong><br>Dr. Revital Marbel: marbelr@hit.ac.il<br>Aviv Elbaz: avivelb@my.hit.ac.il<br>Dr. Harel Berger: harelb@ariel.ac.il</p>
<br>
<p><strong>Ethics Committee:</strong> This study has been approved by the HIT Ethics Committee for Research Involving Human Participants.</p>
"""
blocks.append(block("TEXT", html=STUDY_INFO.strip()))
blocks.append(block("DIVIDER"))

# === Page 2: Participant Details ===
blocks.append(block("TEXT", html="<h2>Participant Details</h2>"))

questions = [
    ("1. Full Name", "INPUT_TEXT"),
    ("2. ID / Passport Number (optional)", "INPUT_TEXT"),
    ("3. Email Address", "INPUT_EMAIL"),
    ("4. Institution", "INPUT_TEXT"),
    ("5. Department", "INPUT_TEXT"),
    ("6. Academic Position (e.g., Professor, Lecturer, Postdoc, PhD Student, Researcher)", "INPUT_TEXT"),
    ("7. Address (optional)", "INPUT_TEXT"),
]

for label_text, input_type in questions:
    blocks.append(block("LABEL", html=f"<p><strong>{label_text}</strong></p>"))
    blocks.append(block(input_type))

# === Consent ===
blocks.append(block("DIVIDER"))
blocks.append(block("TEXT", html="<h2>Consent</h2>"))
blocks.append(block("TEXT", html="""
<p>Please read each statement below. By completing questions 8 and 9, you confirm
that you have read, understood, and agree to all of the following:</p>
<ol>
<li>I confirm that I have read and understood the study information provided above.</li>
<li>I understand that I will be shown simulated phishing emails and asked to rate
their persuasiveness. No phishing emails will be sent to me.</li>
<li>I understand that my participation is entirely voluntary and I may withdraw at
any time without consequences to my employment, academic standing, or student status.</li>
<li>I understand that my ratings will be stored separately from my identity and will
be reported only in aggregated, anonymous form.</li>
<li>I freely agree to participate in this study.</li>
</ol>
""".strip()))

blocks.append(block("LABEL", html="<p><strong>8. Digital Consent: Type your full name "
    "to confirm you agree to all statements above. Together with your signature below, "
    "this serves as your binding digital approval to participate.</strong></p>"))
blocks.append(block("INPUT_TEXT"))

blocks.append(block("LABEL", html="<p><strong>9. Participant Signature: Draw below "
    "to approve your consent to participate.</strong></p>"))
blocks.append(block("SIGNATURE"))

# ---------------------------------------------------------------------------
print(f"Creating form with {len(blocks)} blocks...")
resp = requests.post(
    "https://api.tally.so/forms",
    headers=HEADERS,
    json={"status": "PUBLISHED", "blocks": blocks},
    timeout=30,
)

if resp.status_code == 201:
    d = resp.json()
    fid = d.get("id", "unknown")
    print(f"\nForm created!")
    print(f"  ID:      {fid}")
    print(f"  URL:     https://tally.so/r/{fid}")
    print(f"  Admin:   https://tally.so/forms/{fid}")
else:
    print(f"\nERROR {resp.status_code}: {resp.text[:600]}")
    sys.exit(1)
