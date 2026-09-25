"""Create TKG informed consent form on Tally.so via API.

Participant-facing only, no researcher section.
Verified working block types: INPUT_TEXT, INPUT_EMAIL, INPUT_DATE,
TEXTAREA, SIGNATURE, LABEL, TEXT, FORM_TITLE, DIVIDER.
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
    html="<h1>Informed Consent : Phishing Persuasion Study</h1>",
    title="Informed Consent : Phishing Persuasion Study"))

STUDY_INFO = """
<p><strong>Study Title:</strong> Quantifying Personalized Phishing Risk: From Generic Baselines to Temporal Knowledge Graphs</p>
<p><strong>Principal Investigator:</strong> Dr. Revital Marbel, Holon Institute of Technology (HIT), School of Computer Science</p>
<p><strong>Co-Investigators:</strong> Aviv Elbaz (HIT), Dr. Harel Berger (Ariel University)</p>
<br>
<p><strong>What this study is about:</strong> We are measuring how persuasive AI-generated phishing emails can be when personalized using publicly available information about you (academic publications, public profiles, public social media posts). You may receive up to 3 simulated phishing emails over approximately 3 months.</p>
<br>
<p><strong>Partial deception:</strong> You know you are in a phishing study, but you will not know which specific emails are part of the experiment or exactly when they will arrive. A full debriefing email will be sent to all participants at the end of the study, revealing which emails were part of the experiment and how your public data was used.</p>
<br>
<p><strong>Your data:</strong> We collect only publicly available information about you from open web sources. Click data is stored separately from your identity in encrypted files. All published results are aggregated and anonymous. You may request deletion of all your data at any time.</p>
<br>
<p><strong>Your rights:</strong> Participation is entirely voluntary. You may withdraw at any time and request immediate deletion of all your data, with no consequences to your employment, academic standing, or student status.</p>
<br>
<p><strong>Risk:</strong> Minimal. Possible mild discomfort from awareness that public data was used to personalize emails and the partial uncertainty about which emails are part of the experiment.</p>
<br>
<p><strong>Contact:</strong><br>Dr. Revital Marbel: marbelr@hit.ac.il<br>Aviv Elbaz: avivelb@my.hit.ac.il<br>Dr. Harel Berger: harelb@ariel.ac.il</p>
<br>
<p><strong>Ethics Committee:</strong> This study has been approved by the HIT Ethics Committee for Research Involving Human Participants.</p>
"""
blocks.append(block("TEXT", html=STUDY_INFO.strip()))

# === Page 2: Participant Details ===
blocks.append(block("DIVIDER"))
blocks.append(block("TEXT", html="<h2>Participant Details</h2>"))

questions = [
    ("1. Full Name", "INPUT_TEXT"),
    ("2. ID / Passport Number", "INPUT_TEXT"),
    ("3. Email Address", "INPUT_EMAIL"),
    ("4. Institution", "INPUT_TEXT"),
    ("5. Department", "INPUT_TEXT"),
    ("6. Academic Position (e.g., Professor, Lecturer, Postdoc, PhD Student, Researcher)", "INPUT_TEXT"),
    ("7. Address", "TEXTAREA"),
]

for label_text, input_type in questions:
    blocks.append(block("LABEL", html=f"<p><strong>{label_text}</strong></p>"))
    blocks.append(block(input_type))

# === Consent ===
blocks.append(block("DIVIDER"))
blocks.append(block("TEXT", html="<h2>Consent</h2>"))
blocks.append(block("TEXT", html="""
<p>Please read each statement below. By completing questions 8 and 9, you confirm that you have read, understood, and agree to all of the following:</p>
<ol>
<li>I confirm that I have read and understood the study information provided above.</li>
<li>I understand that the study involves partial deception: I will not know which
emails are part of the experiment or when they will arrive, and I will receive a
full debriefing at the end of the study.</li>
<li>I understand that my participation is entirely voluntary and I may withdraw at
any time without consequences to my employment, academic standing, or student status.</li>
<li>I understand that publicly available information about me will be collected from
open web sources to personalize the simulated phishing emails, and that I may request
deletion of all my data at any time.</li>
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
