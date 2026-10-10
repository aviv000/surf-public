"""Build the full graph-viewer delivery pipeline (single entry point).

Reproducibly: renders depth graphs -> builds the hosted viewer bundle ->
generates the URL card -> writes per-rater delivery bundles -> optionally
deploys to Netlify (requires `netlify-cli login`).

Usage:
  python scripts/build_graph_viewer.py
  python scripts/build_graph_viewer.py --targets ariel-001,ariel-002,hit-001
  python scripts/build_graph_viewer.py --url my-viewer.netlify.app --deploy

Outputs (all gitignored, contain real-person PII):
  outputs/graph_renders/            PNGs + interactive HTML per target
  outputs/graph_viewer/             hosted-site bundle (index + graph HTMLs)
  outputs/graph_viewer_delivery/    per-rater folder: card.png + message.txt
"""

import argparse
import html as html_mod
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

RENDERS_DIR = ROOT / "outputs" / "graph_renders"
VIEWER_DIR = ROOT / "outputs" / "graph_viewer"
DELIVERY_DIR = ROOT / "outputs" / "graph_viewer_delivery"

DEFAULT_URL = "https://aviv000.github.io/tkg-graph-viewer/"
# The rating team's own targets: the graphs the viewers are about.
DEFAULT_TARGETS = "ariel-001,ariel-002,hit-001,tau-002"

RATERS = [
    {"id": "revital", "name": "Revital"},
    {"id": "harel", "name": "Harel"},
    {"id": "aviv", "name": "Aviv"},
]

def _graph_node_index() -> dict:
    """id -> (label, source_url) over the merged graph (for evidence display)."""
    from config import MERGED_GRAPH
    from scripts.render_target_graphs import short_label
    idx = {}
    if MERGED_GRAPH.exists():
        g = json.loads(MERGED_GRAPH.read_text(encoding="utf-8"))
        for ntype, nlist in g.get("nodes", {}).items():
            for n in nlist:
                props = n.get("properties", {})
                idx[n["id"]] = (short_label(ntype, props),
                                props.get("source_url", "") or "")
    return idx


def build_traits_report(targets: str) -> None:
    """traits.html: per-target personality traits from inferences.json with
    evidence and source links; published alongside the viewer."""
    from config import CACHE_DIR
    node_idx = _graph_node_index()
    wanted = {t for t in targets.split(",")}
    sections = []
    for inf_file in sorted(CACHE_DIR.glob("*/inferences.json")):
        tid = inf_file.parent.name
        if wanted and tid not in wanted:
            continue
        try:
            inf = json.loads(inf_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        name = inf.get("target_id", tid)
        rows = []
        for t in sorted(inf.get("traits", []),
                        key=lambda x: -(x.get("confidence") or 0)):
            conf = t.get("confidence") or 0
            if conf <= 0:
                continue
            ev_links = "".join(
                '<a href="' + html_mod.escape(
                    node_idx.get(e, ("", ""))[1] or "#") + '" target="_blank">'
                + html_mod.escape(node_idx.get(e, ("?", ""))[0]) + "</a> "
                for e in t.get("evidence", []))
            rows.append(
                '<tr><td>' + html_mod.escape(t.get("trait", "?")) + "</td>"
                '<td><div class="bar"><div style="width:' + str(int(conf * 100))
                + '%"></div></div></td><td>' + f"{conf:.2f}" + "</td>"
                "<td>" + html_mod.escape(t.get("rationale", "")) + "</td>"
                "<td>" + (ev_links or "-") + "</td></tr>")
        open_rows = []
        for o in inf.get("open_insights", []):
            ev_links = "".join(
                '<a href="' + html_mod.escape(
                    node_idx.get(e, ("", ""))[1] or "#") + '" target="_blank">'
                + html_mod.escape(node_idx.get(e, ("?", ""))[0]) + "</a> "
                for e in o.get("evidence", []))
            open_rows.append(
                "<li><b>" + html_mod.escape(str(o.get("insight", "?")))
                + "</b> (" + f"{o.get('confidence', 0):.2f}" + ") - "
                + html_mod.escape(o.get("rationale", ""))
                + " [evidence: " + (ev_links or "none") + "]</li>")
        sections.append(
            "<section><h2>" + html_mod.escape(name) + "</h2>"
            '<p class="meta">graph depth ' + str(inf.get("graph_depth", "?"))
            + " | " + str(inf.get("generated_at", "")) + "</p>"
            "<table><tr><th>Trait</th><th>Confidence</th><th></th>"
            "<th>Rationale</th><th>Evidence</th></tr>"
            + "".join(rows) + "</table>"
            "<h3>Open insights</h3><ul>"
            + ("".join(open_rows) or "<li>none</li>") + "</ul></section>")
    page = (
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">\n"
        "<title>TKG Inference Report - Personality Traits</title>\n"
        "<style>\n"
        "body { font-family: sans-serif; max-width: 960px; margin: 30px auto; "
        "padding: 0 16px; color: #222; }\n"
        "h1 { font-size: 1.5em; }\n"
        "section { margin: 28px 0; padding: 16px; border: 1px solid #ddd; "
        "border-radius: 8px; }\n"
        "table { width: 100%; border-collapse: collapse; }\n"
        "th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #eee; "
        "vertical-align: top; }\n"
        ".bar { background: #eee; width: 110px; height: 10px; border-radius: 5px; }\n"
        ".bar div { background: #8e44ad; height: 10px; border-radius: 5px; }\n"
        "a { color: #1a56a0; }\n"
        ".meta { color: #777; font-size: .85em; }\n"
        "li { margin: 6px 0; }\n"
        "</style></head><body>\n"
        "<h1>TKG Inference Report - Personality Traits</h1>\n"
        "<p>Level-2 inference layer: the 10-trait catalog (Big-5 plus "
        "persuasion susceptibility) scored against each target's knowledge "
        "graph, plus open-discovery insights. Confidence bars are purple; "
        "evidence links open the source pages.</p>\n"
        + "\n".join(sections) +
        "\n</body></html>"
    )
    page += _trait_distance_matrix()

    (VIEWER_DIR / "traits.html").write_text(page, encoding="utf-8")
    print("traits.html written to viewer bundle")


def _trait_distance_matrix() -> str:
    """Pairwise trait closeness between targets, via shared trait nodes
    (demo-2 feedback: 'weight on the edge', distances between people)."""
    from config import MERGED_GRAPH
    if not MERGED_GRAPH.exists():
        return ""
    g = json.loads(MERGED_GRAPH.read_text(encoding="utf-8"))
    person_names = {}
    for n in g.get("nodes", {}).get("person", []):
        nm = n.get("properties", {}).get("full_name", "")
        if nm in ("Revital Marbel", "Harel Berger", "Aviv Elbaz",
                  "Gahl Silverman"):
            person_names[n["id"]] = nm
    person_conf = {}
    for e in g.get("edges", {}).get("EXHIBITS", []):
        person_conf.setdefault(e["from"], {})[e["to"]] = (
            e.get("properties", {}).get("confidence") or 0)
    people = sorted(person_names)
    if len(people) < 2:
        return ""
    html = ['<h2>Trait closeness between people</h2>',
            '<p>Closeness = sum of average confidence over traits both '
            'people exhibit. The weight on the EXHIBITS edge is the '
            'confidence.</p>',
            '<table><tr><th></th>' + ''.join(
                f'<th>{html_mod.escape(person_names[p].split()[0])}</th>'
                for p in people) + '</tr>']
    for a in people:
        row = [f'<th>{html_mod.escape(person_names[a].split()[0])}</th>']
        for b in people:
            if a == b:
                row.append('<td>-</td>')
                continue
            shared = set(person_conf.get(a, {})) & set(person_conf.get(b, {}))
            closeness = sum(
                (person_conf[a][t] + person_conf[b][t]) / 2
                for t in shared)
            row.append(f'<td>{closeness:.2f}</td>')
        html.append('<tr>' + ''.join(row) + '</tr>')
    html.append('</table>')
    return ''.join(html)


INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TKG Internal Pilot — Graph Viewer</title>
<style>
body {{ font-family: sans-serif; max-width: 720px; margin: 40px auto; padding: 0 16px; color: #222; }}
h1 {{ font-size: 1.4em; }}
a {{ display: block; margin: 12px 0; font-size: 1.15em; color: #1a56a0; }}
.note {{ color: #666; font-size: .9em; }}
</style>
</head>
<body>
<h1>TKG Internal Pilot — Graph Viewer</h1>
<p>Open a graph to explore what the model knew at each depth (use the Depth 1 / Depth 2 toggle inside each page).</p>
{links}
<p><a href="traits.html">Personality traits report (inference layer)</a></p>
<p class="note">Internal research material. Do not share outside the rating team.</p>
</body>
</html>
"""


def render_graphs(targets: str) -> list[str]:
    """Run the depth renderer; return the list of target slugs rendered."""
    import pandas as pd
    from config import TARGETS_CSV
    df = pd.read_csv(TARGETS_CSV)
    ids = (set(targets.split(",")) if targets != "all"
           else {r["target_id"] for r in df.to_dict("records")
                 if not r["target_id"].startswith("syn-")})
    subprocess.run([sys.executable, str(ROOT / "scripts" / "render_target_graphs.py"),
                    "--targets", ",".join(sorted(ids))], check=True)
    return [i.replace("-", "_") for i in sorted(ids)]


def build_viewer_bundle(slugs: list[str], names: dict[str, str]) -> None:
    VIEWER_DIR.mkdir(parents=True, exist_ok=True)
    links = "\n".join(
        f'<a href="{s}_graph.html">{names[s]} — knowledge graph</a>' for s in slugs)
    (VIEWER_DIR / "index.html").write_text(
        INDEX_TEMPLATE.format(links=links), encoding="utf-8")
    copied = 0
    for s in slugs:
        src = RENDERS_DIR / f"{s}_graph.html"
        if not src.exists():
            print(f"  WARNING: no render for {s} (target not in merged graph) — skipped")
            continue
        shutil.copy(src, VIEWER_DIR / f"{s}_graph.html")
        for png in sorted(RENDERS_DIR.glob(f"{s}*.png")):
            shutil.copy(png, VIEWER_DIR / png.name)
        copied += 1
    print(f"viewer bundle built at {VIEWER_DIR} ({copied} graphs, PNGs included)")


def generate_url_card(url: str, public: bool = False) -> None:
    """URL card PNG (no QR): the clickable link is the URL itself."""
    from PIL import Image, ImageDraw, ImageFont
    card = Image.new("RGB", (2400, 1000), "white")
    d = ImageDraw.Draw(card)
    f1 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 96)
    f2 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 88)
    f3 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
    d.text((60, 60), "TKG Internal Pilot", fill="black", font=f1)
    d.text((60, 200), "Knowledge Graph Viewer", fill="black", font=f1)
    d.rectangle([60, 360, 2260, 480], outline="#1a56a0", width=3)
    d.text((90, 382), url, fill="#1a56a0", font=f2)
    if not public:
        d.text((60, 560), "Password shared with the rating team.", fill="#444", font=f3)
    d.text((60, 640), "Open the link, choose a graph, use the Depth 1 / Depth 2 toggle.",
           fill="#444", font=f3)
    out = RENDERS_DIR / "graph_viewer_link.png"
    card.save(out)
    print(f"URL card saved: {out}")


def write_deliveries(url: str, public: bool = False) -> None:
    """Per-rater delivery bundle: card copy + ready-to-send message."""
    card = RENDERS_DIR / "graph_viewer_link.png"
    for rater in RATERS:
        d = DELIVERY_DIR / rater["id"]
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy(card, d / "card.png")
        password_line = "" if public else "(password: the one we shared)\n"
        message = (
            f"Hi {rater['name']},\n\n"
            f"For the graph-depth review: the knowledge graph viewer is live at\n"
            f"{url}\n"
            f"{password_line}\n"
            f"Open it, pick any graph, and flip Depth 1 / Depth 2 to see how "
            f"depth changes what the model knew about each of us.\n\n"
            f"Card attached. — Aviv\n"
        )
        (d / "message.txt").write_text(message, encoding="utf-8")
        print(f"delivery bundle: {d} (card.png + message.txt)")


PAGES_REPO = "https://github.com/aviv000/tkg-graph-viewer.git"
PAGES_REPO_DIR = ROOT / "outputs" / "graph_viewer_repo"


def deploy() -> None:
    """Deploy the bundle to GitHub Pages (public repo aviv000/tkg-graph-viewer).
    Netlify was retired 2026-09-23 after its free credits ran out."""
    if not PAGES_REPO_DIR.exists():
        subprocess.run(["git", "clone", PAGES_REPO, str(PAGES_REPO_DIR)],
                       check=True)
    for item in VIEWER_DIR.iterdir():
        dst = PAGES_REPO_DIR / item.name
        if item.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(item, dst)
        else:
            shutil.copy2(item, dst)
    subprocess.run(["git", "add", "-A"], cwd=PAGES_REPO_DIR, check=True)
    changed = subprocess.run(["git", "status", "--porcelain"],
                             cwd=PAGES_REPO_DIR, capture_output=True,
                             text=True).stdout.strip()
    if changed:
        subprocess.run(["git", "-c", "user.email=aviv6u6@gmail.com",
                        "-c", "user.name=Aviv", "commit", "-m", "viewer update"],
                       cwd=PAGES_REPO_DIR, check=True)
        subprocess.run(["git", "push"], cwd=PAGES_REPO_DIR, check=True)
        print(f"Deployed to GitHub Pages: {DEFAULT_URL}")
    else:
        print(f"Viewer repo already up to date: {DEFAULT_URL}")


def main():
    parser = argparse.ArgumentParser(
        description="Build graph-viewer delivery pipeline end to end")
    parser.add_argument("--targets", type=str, default=DEFAULT_TARGETS,
                        help="Comma-separated target_ids (default: the team targets)")
    parser.add_argument("--url", type=str, default=DEFAULT_URL)
    parser.add_argument("--deploy", action="store_true",
                        help="Deploy the viewer bundle to GitHub Pages")
    parser.add_argument("--public", action="store_true",
                        help="Site is public: omit password lines from card and messages")
    args = parser.parse_args()

    import pandas as pd
    from config import TARGETS_CSV
    df = pd.read_csv(TARGETS_CSV)
    names = {r["target_id"].replace("-", "_"): r["full_name"]
             for r in df.to_dict("records")}

    slugs = render_graphs(args.targets)
    build_viewer_bundle(slugs, names)
    build_traits_report(args.targets)
    generate_url_card(args.url, public=args.public)
    write_deliveries(args.url, public=args.public)
    if args.deploy:
        deploy()
        print(f"\nDeployed: {args.url}")


if __name__ == "__main__":
    main()
