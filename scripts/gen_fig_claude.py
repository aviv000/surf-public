"""Generate pipeline figure using Claude API."""
import sys
sys.path.insert(0, '/mnt/data/git/spear-phishing-llm')
from agents.llm_utils import llm_call
from pathlib import Path

system = """You are an expert data visualization designer. Write complete, working Python matplotlib code for publication-quality IEEE academic paper figures. Use clean minimal design, FancyBboxPatch for rounded boxes, proper spacing, professional colors (blues, grays, muted oranges), clear labels, proper arrows, self-contained code, save using Path. Do NOT use plt.show()."""

prompt = """Create a clean pipeline figure. Two panels (subplots) in one figure, 6.5 x 5 inches.

TOP PANEL "Generation Phase": 4 boxes with arrows between them:
1. "100 Synthetic Personas" (gray box, sub-label: "Academic + Professional Profiles")
2. "2x2 Stimulus Construction" (orange box, sub-label: "Surface x Content")
3. "GPT-4.1 + Claude Sonnet 4.6" (blue+green split box, sub-label: "Two Generators")
4. "400 Emails" (gray box, sub-label: "4 variants x 100 personas")

BOTTOM PANEL "Evaluation Phase": 4 boxes with arrows between them:
1. "Blind Pairwise Presentation" (gray box, sub-label: "Email 1 / Email 2")
2. "4-Judge Cross-Family Panel" (blue box, sub-label: "GPT-4.1-mini, DeepSeek-Chat, Claude, Gemini")
3. "Analysis Suite" (orange box, sub-label: "Win Rates, Agreement Kappa, Introspection")
4. "Diagnostic Output" (green box, sub-label: "Surface Stripping if bias detected")

Include a connecting label between the two panels: "Same stimuli feed all paths"

Save to figures/pipeline_claude.pdf. Write ONLY the Python code. No markdown. No explanation."""

resp = llm_call(system, prompt, model='claude-sonnet-4-6', max_tokens=4096, temperature=0.1)

out_path = Path('/mnt/data/git/spear-phishing-llm/publish/surf_revised_new/figures/gen_pipeline_claude.py')
code = resp.strip() if resp else ""
if code.startswith('```'):
    code = code[code.index('\n')+1:]
if code.endswith('```'):
    code = code[:-3]
out_path.write_text(code)
print(f"Saved {len(code)} chars")
