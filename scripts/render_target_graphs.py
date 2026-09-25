"""Render per-target KG depth visualizations (viewer v2).

Static PNGs + a self-contained interactive HTML per target with:
- depth buttons 1-4
- year slider (temporal filter over nodes/edges)
- click-to-source: node click opens its source_url
- English-label preference with RTL isolation fallback
- the target's own social profiles hidden by default (toggle)
- Trait nodes (purple) + dashed EXHIBITS edges; clicking a trait node
  highlights its evidence nodes

Usage:
  python scripts/render_target_graphs.py --targets ariel-001,ariel-002,hit-001
  python scripts/render_target_graphs.py --targets all --out outputs/graph_renders

Outputs are gitignored — they contain real-person PII.
"""

import argparse
import html as html_mod
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import CACHE_DIR, MERGED_GRAPH  # noqa: E402

OUT_DIR = ROOT / "outputs" / "graph_renders"
VIS_DIR = ROOT / "lib" / "vis-9.1.2"

HEBREW_RE = re.compile(r"[֐-׿]")

METHOD_COLORS = {"catalog": "#8e44ad", "open": "#2980b9"}


def _trait_color(ntype, props):
    if ntype == "trait":
        return METHOD_COLORS.get(props.get("method", "catalog"), "#8e44ad")
    return COLORS.get(ntype, "#999999")


COLORS = {
    "person": "#e15759", "paper": "#4e79a7", "venue": "#59a14f",
    "institution": "#9c755f", "socialprofile": "#edc948",
    "lifeevent": "#d37295", "interest": "#76b7b2", "location": "#f28e2b",
    "education": "#b07aa1", "funding": "#86bcb6", "teaching": "#ff9da7",
    "organization": "#b6992d", "trait": "#8e44ad",
}

_LABEL_KEYS = {
    "person": "full_name", "paper": "title", "venue": "name",
    "institution": "name", "socialprofile": "handle", "lifeevent": "title",
    "interest": "topic", "location": "city", "education": "institution",
    "funding": "grant_title", "teaching": "course_name", "organization": "org_name",
    "trait": "name",
}

MAX_DEPTH = 4
YEAR_MIN, YEAR_MAX = 2005, 2026


def _node_year(props: dict) -> int | None:
    for key in ("year", "start_year"):
        v = props.get(key)
        if isinstance(v, int) and v:
            return v
    date = props.get("date")
    if isinstance(date, str) and len(date) >= 4:
        try:
            return int(date[:4])
        except ValueError:
            return None
    return None


def _edge_year(props: dict) -> int | None:
    for key in ("year", "first_year", "last_year"):
        v = props.get(key)
        if isinstance(v, int) and v:
            return v
    papers = props.get("papers")
    if isinstance(papers, list) and papers:
        years = [p.get("year") for p in papers if isinstance(p, dict)]
        if years:
            return max(y for y in years if isinstance(y, int))
    return _node_year(props)


def _props_lines(props: dict, max_lines: int = 12) -> str:
    """Human-readable tooltip lines: 'Key: value' per property, no JSON blob."""
    lines = []
    for k, v in props.items():
        if k.startswith("_source_"):
            continue
        if v is None or v == "":
            continue
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)[:120]
        lines.append(f"<b>{html_mod.escape(str(k))}</b>: "
                     f"{html_mod.escape(str(v))[:140]}")
        if len(lines) >= max_lines:
            break
    return "<br>".join(lines)


def short_label(ntype: str, props: dict) -> str:
    """English preference: primary key first; if the label has Hebrew chars,
    try common English alternatives; finally RTL-isolate mixed content."""
    candidates = [props.get(_LABEL_KEYS.get(ntype, "")),
                  props.get("name"), props.get("title"),
                  props.get("full_name"), props.get("topic")]
    label = ""
    for c in candidates:
        if c and str(c).strip():
            label = str(c).replace("\n", " ")
            break
    if not label:
        label = ntype
    if HEBREW_RE.search(label):
        # prefer an English variant if available; else isolate for readability
        eng = next((str(c) for c in candidates
                    if c and not HEBREW_RE.search(str(c))), None)
        if eng:
            label = str(eng).replace("\n", " ")
        else:
            label = f"‫{label}‬"
    return label[:40] if len(label) > 40 else label


def load_graph() -> dict:
    if not MERGED_GRAPH.exists():
        print(f"ERROR: {MERGED_GRAPH} not found. Run the integrator first.")
        sys.exit(1)
    return json.loads(MERGED_GRAPH.read_text(encoding="utf-8"))


def subgraph_at_depth(g: dict, target_id: str, depth: int) -> tuple[list, list]:
    """Nodes within `depth` hops of the target + edges among them."""
    edges = g.get("edges", {})
    adjacency = {}
    for etype, elist in edges.items():
        for e in elist:
            adjacency.setdefault(e["from"], []).append((e["to"], etype))
            adjacency.setdefault(e["to"], []).append((e["from"], etype))
    visited = {target_id}
    frontier = [target_id]
    for _ in range(depth):
        nxt = []
        for nid in frontier:
            for (other, _e) in adjacency.get(nid, []):
                if other not in visited:
                    visited.add(other)
                    nxt.append(other)
        frontier = nxt

    node_entries = []
    known_ids = set()
    for ntype, nlist in g.get("nodes", {}).items():
        for n in nlist:
            if n["id"] in visited:
                node_entries.append((n["id"], ntype, n.get("properties", {})))
                known_ids.add(n["id"])
    edge_entries = []
    for etype, elist in edges.items():
        for e in elist:
            if e["from"] in visited and e["to"] in visited:
                edge_entries.append((e["from"], e["to"], etype,
                                     e.get("properties", {})))
    # Edge-only endpoints: the extractor sometimes emits edges whose nodes
    # have no record. Synthesize placeholders so renderers never meet an
    # attribute-less node.
    for e in edge_entries:
        for nid in (e[0], e[1]):
            if nid in known_ids or nid not in visited:
                continue
            ntype = nid.split(":", 1)[0] if ":" in nid else "unknown"
            label = nid.split(":", 1)[-1].replace("_", " ").title()
            node_entries.append((nid, ntype, {"full_name": label}))
            known_ids.add(nid)
    return node_entries, edge_entries


def visible_entries(entries, hide_self_profiles, target_pid, self_profile_ids):
    if not hide_self_profiles:
        return entries
    return [e for e in entries if e[0] not in self_profile_ids]


def collect_self_profiles(entries, target_pid, edges):
    """SocialProfile nodes directly HAS_PROFILE-linked to the target."""
    own = set()
    for frm, to, etype, props in edges:
        if etype == "HAS_PROFILE" and frm == target_pid:
            own.add(to)
    return {e[0] for e in entries if e[0] in own}


# ---------------------------------------------------------------------------
# Static PNGs
# ---------------------------------------------------------------------------

def render_png(node_entries, edge_entries, target_name, depth, path: Path,
               hide_self_profiles=True):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import networkx as nx

    target_pid = next((n[0] for n in node_entries
                       if n[1] == "person"
                       and n[2].get("full_name") == target_name), None)
    if not target_pid:
        target_pid = next((n[0] for n in node_entries if n[1] == "person"), None)
    own = collect_self_profiles(node_entries, target_pid, edge_entries)
    if hide_self_profiles and own:
        node_entries = [e for e in node_entries if e[0] not in own]
        edge_entries = [e for e in edge_entries if e[0] not in own and e[1] not in own]

    G = nx.Graph()
    for nid, ntype, props in node_entries:
        G.add_node(nid, label=short_label(ntype, props),
                   color=COLORS.get(ntype, "#999999"))
    for frm, to, etype, props in edge_entries:
        G.add_edge(frm, to, etype=etype)

    pos = nx.spring_layout(G, k=2.2, seed=42, iterations=120)
    colors = [G.nodes[n]["color"] for n in G.nodes]
    labels = {n: G.nodes[n]["label"][:22] for n in G.nodes}

    fig, ax = plt.subplots(figsize=(14, 10))
    dashed = [(f, t) for f, t, e in G.edges(data=True) if e["etype"] == "EXHIBITS"]
    solid = [(f, t) for f, t, e in G.edges(data=True) if e["etype"] != "EXHIBITS"]
    nx.draw_networkx_edges(G, pos, edgelist=solid, alpha=0.35, ax=ax)
    nx.draw_networkx_edges(G, pos, edgelist=dashed, alpha=0.6, style="dashed",
                           edge_color="#8e44ad", ax=ax)
    nx.draw_networkx_nodes(G, pos, node_color=colors, node_size=340, ax=ax)
    nx.draw_networkx_labels(G, pos, labels, font_size=7, ax=ax)
    ax.set_title(f"{target_name} — depth {depth} ({len(node_entries)} nodes, "
                 f"{len(edge_entries)} edges)", fontsize=12)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def render_side_by_side(entries1, edges1, entries2, edges2, target_name, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import networkx as nx

    fig, axes = plt.subplots(1, 2, figsize=(24, 10))
    for ax, (entries, edges, depth) in zip(
            axes, [(entries1, edges1, 1), (entries2, edges2, 2)]):
        G = nx.Graph()
        for nid, ntype, props in entries:
            G.add_node(nid, label=short_label(ntype, props),
                       color=COLORS.get(ntype, "#999999"))
        for frm, to, _et, _pr in edges:
            G.add_edge(frm, to)
        pos = nx.spring_layout(G, k=2.2, seed=42, iterations=120)
        colors = [G.nodes[n]["color"] for n in G.nodes]
        labels = {n: G.nodes[n]["label"][:22] for n in G.nodes}
        nx.draw_networkx_edges(G, pos, alpha=0.35, ax=ax)
        nx.draw_networkx_nodes(G, pos, node_color=colors, node_size=300, ax=ax)
        nx.draw_networkx_labels(G, pos, labels, font_size=6, ax=ax)
        ax.set_title(f"Depth {depth} — {len(G.nodes)} nodes, {len(G.edges)} edges",
                     fontsize=11)
        ax.axis("off")
    fig.suptitle(f"{target_name} — how graph depth changes the graph", fontsize=14)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Interactive HTML (viewer v2)
# ---------------------------------------------------------------------------

def render_html(all_entries_by_depth, all_edges_by_depth, target_name,
                target_pid, path: Path):
    vis_js = (VIS_DIR / "vis-network.min.js").read_text(encoding="utf-8")
    vis_css = (VIS_DIR / "vis-network.css").read_text(encoding="utf-8")

    def vis_dataset(entries, edges):
        own = collect_self_profiles(entries, target_pid, edges)
        nodes = []
        seen_ids = set()
        label_map = {nid: short_label(ntype, props)
                     for nid, ntype, props in entries}
        method_map = {nid: props.get("method", "catalog")
                      for nid, ntype, props in entries
                      if ntype == "trait"}
        for nid, ntype, props in entries:
            if nid in seen_ids:
                continue  # graph-level id collisions must never break the viewer
            seen_ids.add(nid)
            url = props.get("source_url", "") or ""
            nodes.append({
                "id": nid,
                "label": short_label(ntype, props),
                "color": {"background": _trait_color(ntype, props),
                          "border": "#333"},
                "year": _node_year(props),
                "url": url,
                "ntype": ntype,
                "own": nid in own,
                "tip": (f"<b>{html_mod.escape(ntype)}</b>: "
                        f"{html_mod.escape(short_label(ntype, props))}<br>"
                        f"{_props_lines(props)}"
                        + (f"<br><a href='{html_mod.escape(url)}' "
                           f"target='_blank'>source</a>"
                           if url else "")),
            })
        ed = []
        for frm, to, etype, props in edges:
            if etype == "EXHIBITS":
                conf = props.get("confidence", 0) or 0
                ev = [label_map.get(i, i) for i in props.get("evidence", [])]
                tip = (f"<b>{html_mod.escape(etype)}</b> (confidence "
                       f"{conf:.2f})<br>"
                       f"{html_mod.escape(str(props.get('rationale', '')))}<br>"
                       f"<b>Evidence:</b> "
                       f"{html_mod.escape(', '.join(str(x) for x in ev)[:400])}")
                width = 1 + 5 * conf
                edge_color = METHOD_COLORS.get(
                    method_map.get(to, "catalog"), "#8e44ad")
                ed.append({
                    "from": frm, "to": to, "label": etype,
                    "dashes": True,
                    "color": {"color": edge_color},
                    "width": width,
                    "year": _edge_year(props),
                    "tip": tip,
                })
            else:
                ed.append({
                    "from": frm, "to": to, "label": etype,
                    "year": _edge_year(props),
                    "tip": (f"<b>{html_mod.escape(etype)}</b><br>"
                            f"{_props_lines(props, max_lines=8)}"),
                })
        return {"nodes": nodes, "edges": ed}

    depth_datasets = {}
    for d in sorted(all_entries_by_depth):
        depth_datasets[d] = vis_dataset(
            all_entries_by_depth[d], all_edges_by_depth[d])

    evidence_map = {}
    for d in sorted(all_entries_by_depth):
        for frm, to, etype, props in all_edges_by_depth[d]:
            if etype == "EXHIBITS":
                evidence_map[to] = props.get("evidence", [])

    html_doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{html_mod.escape(target_name)} — KG depth</title>
<style>{vis_css}
body {{ font-family: sans-serif; margin: 0; }}
#header {{ padding: 10px 16px; background: #f5f5f5; border-bottom: 1px solid #ccc; }}
#header button {{ margin-right: 6px; padding: 5px 12px; cursor: pointer; }}
#header button.active {{ background: #4e79a7; color: #fff; border: 1px solid #4e79a7; }}
#header label {{ margin-left: 12px; }}
#net {{ height: calc(100vh - 120px); }}
#tip {{
  position: fixed; display: none; max-width: 560px;
  background: #fff; border: 1px solid #ccc; border-radius: 6px;
  padding: 8px 12px; font-size: 13px; line-height: 1.45;
  box-shadow: 0 2px 10px rgba(0,0,0,.15); z-index: 9999;
  pointer-events: none; color: #222;
}}
#tip a {{ color: #1a56a0; pointer-events: auto; }}
</style></head>
<body>
<div id="header">
<h2 style="margin:4px 0">{html_mod.escape(target_name)} — knowledge graph by depth and time</h2>
{''.join(f'<button id="b{d}" class="{"active" if d == min(depth_datasets) else ""}" onclick="show({d})">Depth {d}</button>' for d in sorted(depth_datasets))}
<label><input type="checkbox" id="selfprof" onchange="show(current)"> show own social profiles</label>
<label>Year: <input type="range" id="yslider" min="{YEAR_MIN}" max="{YEAR_MAX}" value="{YEAR_MAX}" oninput="yearChanged(this.value)"> <span id="ylabel">{YEAR_MAX}</span></label>
<span id="stat" style="margin-left:16px;color:#555"></span>
</div>
<div id="net"></div>
<div id="tip"></div>
<script>{vis_js}</script>
<script>
const RAW = {json.dumps(depth_datasets, ensure_ascii=False)};
const EVIDENCE = {json.dumps(evidence_map, ensure_ascii=False)};
const container = document.getElementById('net');
let network = null, current = 1, currentYear = {YEAR_MAX};

function show(d) {{
  current = d;
  const ds = RAW[d];
  if (!ds) return;
  document.querySelectorAll('#header button').forEach(b =>
    b.className = Number(b.id.slice(1)) === d ? 'active' : '');
  const showOwn = document.getElementById('selfprof').checked;
  const nodes = ds.nodes.filter(n =>
    (n.year == null || n.year <= currentYear) && (showOwn || !n.own));
  const nset = new vis.DataSet(nodes);
  const eset = new vis.DataSet(ds.edges.filter(e =>
    e.year == null || e.year <= currentYear));
  document.getElementById('stat').textContent =
    nset.length + ' nodes, ' + eset.length + ' edges';
  const options = {{
    physics: {{
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {{ gravitationalConstant: -60, springLength: 150, avoidOverlap: 0.25 }},
      stabilization: {{ enabled: true, iterations: 800, fit: true }},
    }},
    nodes: {{ shape: 'dot', size: 14, font: {{ size: 13 }} }},
    edges: {{ arrows: 'to', font: {{ size: 9, align: 'middle' }}, smooth: true }},
  }};
  if (network) network.destroy();
  network = new vis.Network(container, {{nodes: nset, edges: eset}}, options);
  window.network = network;  // exposed for debugging and tests
  const tip = document.getElementById('tip');
  function moveTip(e) {{
    tip.style.display = 'block';
    tip.style.left = Math.min(e.clientX + 14, window.innerWidth - 440) + 'px';
    tip.style.top = (e.clientY + 14) + 'px';
  }}
  network.on('click', params => {{
    const nid = params.nodes[0];
    if (!nid) return;
    const node = nset.get(nid);
    if (node && node.url) window.open(node.url, '_blank');
    if (EVIDENCE[nid]) network.selectNodes(EVIDENCE[nid].concat([nid]));
  }});
  // Hover tooltip via vis's picking API (hoverNode events proved unreliable
  // in this vis-network build, and its built-in popup renders plain text).
  const canvas = container.querySelector('canvas');
  canvas.addEventListener('mousemove', e => {{
    const rect = canvas.getBoundingClientRect();
    // getNodeAt takes canvas-relative DOM coordinates directly (verified:
    // DOMtoCanvas double-applies the fit transform)
    const cp = {{x: e.clientX - rect.left, y: e.clientY - rect.top}};
    const nid = network.getNodeAt(cp);
    if (nid) {{
      const n = nset.get(nid);
      if (n && n.tip) {{ tip.innerHTML = n.tip; moveTip(e); return; }}
    }}
    const eid = network.getEdgeAt(cp);
    if (eid) {{
      const ed = eset.get(eid);
      if (ed && ed.tip) {{ tip.innerHTML = ed.tip; moveTip(e); return; }}
    }}
    tip.style.display = 'none';
  }});
}}
function yearChanged(v) {{
  currentYear = Number(v);
  document.getElementById('ylabel').textContent = v;
  show(current);
}}
const urlDepth = Number(new URLSearchParams(window.location.search).get('depth'));
show(RAW[urlDepth] ? urlDepth : {min(depth_datasets)});
</script>
</body></html>"""
    path.write_text(html_doc, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Render target KG depth graphs")
    parser.add_argument("--targets", type=str, required=True,
                        help="Comma-separated target_ids (or 'all' for targets.csv)")
    parser.add_argument("--out", type=str, default=str(OUT_DIR))
    args = parser.parse_args()

    import pandas as pd
    from config import TARGETS_CSV
    df = pd.read_csv(TARGETS_CSV)
    if args.targets == "all":
        rows = [r for r in df.to_dict("records")
                if not r["target_id"].startswith("syn-")]
    else:
        ids = set(args.targets.split(","))
        rows = [r for r in df.to_dict("records") if r["target_id"] in ids]

    g = load_graph()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for row in rows:
        tid = row["target_id"]
        name = row["full_name"]
        target_pid = None
        for ntype, nlist in g.get("nodes", {}).items():
            for n in nlist:
                if ntype == "person" and (
                        name.lower() in n.get("properties", {}).get("full_name", "").lower()):
                    target_pid = n["id"]
                    break
            if target_pid:
                break
        if not target_pid:
            print(f"[{tid}] target person node not found in merged graph — skipping")
            continue

        entries_by_depth = {}
        edges_by_depth = {}
        for d in range(1, MAX_DEPTH + 1):
            entries_by_depth[d], edges_by_depth[d] = subgraph_at_depth(g, target_pid, d)

        slug = tid.replace("-", "_")
        for d in sorted(entries_by_depth):
            render_png(entries_by_depth[d], edges_by_depth[d], name, d,
                       out / f"{slug}_depth{d}.png")
        render_side_by_side(entries_by_depth[1], edges_by_depth[1],
                            entries_by_depth[2], edges_by_depth[2], name,
                            out / f"{slug}_depths_side_by_side.png")
        render_html(entries_by_depth, edges_by_depth, name, target_pid,
                    out / f"{slug}_graph.html")
        sizes = ", ".join(f"d{d}={len(entries_by_depth[d])}"
                          for d in sorted(entries_by_depth))
        print(f"[{tid}] {sizes} → {out / (slug + '_graph.html')}")

    print(f"\nRenders written to {out}")


if __name__ == "__main__":
    main()
