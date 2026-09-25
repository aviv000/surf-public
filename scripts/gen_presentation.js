const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "Aviv Elbaz";
pres.title = "TKG Methodology + SURF Audit Pipeline";

// ── PALETTE: Midnight Executive ──
const NAVY = "1E2761";
const ICE = "CADCFC";
const WHITE = "FFFFFF";
const DARK = "0D1137";
const GRAY = "8892A6";
const ACCENT = "FF6B35"; // warm accent for highlights

// ── HELPERS ──
function bg(slide, color) { slide.background = { fill: color }; }

function titleBar(slide, text) {
  slide.addText(text, { x: 0.6, y: 0.2, w: 8.8, h: 0.75, fontSize: 28, fontFace: "Cambria", bold: true, color: NAVY, lineSpacingMultiple: 1.1 });
  slide.addShape(pres.ShapeType.rect, { x: 0.6, y: 1.15, w: 1.5, h: 0.04, fill: { color: ACCENT } });
}

function subtitle(slide, text) {
  slide.addText(text, { x: 0.6, y: 1.3, w: 8.8, h: 0.35, fontSize: 13, fontFace: "Calibri", color: GRAY });
}

function bodyBox(slide, x, y, w, h, text, opts = {}) {
  slide.addShape(pres.ShapeType.roundRect, { x, y, w, h, fill: { color: WHITE }, shadow: { type: "outer", blur: 6, offset: 2, color: "000000", opacity: 0.08 }, rectRadius: 0.1 });
  slide.addText(text, { x: x + 0.2, y: y + 0.15, w: w - 0.4, h: h - 0.3, fontSize: opts.fontSize || 12, fontFace: "Calibri", color: DARK, valign: "top", bold: opts.bold });
}

function arrow(slide, x, y, w, h) {
  slide.addText("→", { x, y, w, h, fontSize: 24, color: ACCENT, align: "center", valign: "middle", bold: true });
}

// ══════════════════════════════════════════════
// SLIDE 1 — TITLE
// ══════════════════════════════════════════════
const s1 = pres.addSlide();
bg(s1, NAVY);
s1.addText("Temporal Knowledge Graph\nfor Spear-Phishing Personalization", { x: 0.6, y: 1.2, w: 8.8, h: 1.6, fontSize: 36, fontFace: "Cambria", bold: true, color: WHITE, lineSpacingMultiple: 1.2 });
s1.addShape(pres.ShapeType.rect, { x: 0.6, y: 2.9, w: 2.5, h: 0.04, fill: { color: ACCENT } });
s1.addText("with SURF LLM-as-Judge Audit Pipeline", { x: 0.6, y: 3.1, w: 8.8, h: 0.6, fontSize: 18, fontFace: "Calibri", color: ICE });
s1.addText("Aviv Elbaz · Revital Marbel · Harel Berger · Florian Alt\nHIT · Ariel University · LMU Munich", { x: 0.6, y: 4.3, w: 8.8, h: 0.7, fontSize: 13, fontFace: "Calibri", color: GRAY });

// ══════════════════════════════════════════════
// SLIDE 2 — THE PROBLEM
// ══════════════════════════════════════════════
const s2 = pres.addSlide();
bg(s2, WHITE);
titleBar(s2, "LLM-as-Judge Panels Are Surface-Biased");
subtitle(s2, "SURF protocol findings across 4 frontier judges (N=100 each)");
// Bar chart — single series, 4 judges
s2.addChart(pres.ChartType.bar, [{ name: "Surface Preference Rate (%)", labels: ["Claude\nSonnet 4.6", "DeepSeek\nChat", "GPT-4.1\nMini", "Gemini\n2.5 Flash"], values: [47, 57, 67, 72] }], {
  x: 0.6, y: 1.8, w: 4.5, h: 2.5,
  showTitle: false,
  chartColors: [NAVY],
  catAxisLabelColor: DARK, catAxisLabelFontSize: 10,
  valAxisLabelColor: DARK,
  valAxisMinVal: 0, valAxisMaxVal: 100,
  showValue: true, dataLabelPosition: "outEnd", dataLabelColor: DARK, dataLabelFontSize: 14, dataLabelFontFace: "Calibri",
  valGridLine: { color: "E0E0E0", size: 0.5 },
  catGridLine: { style: "none" },
  showLegend: false,
  barDir: "bar",
});
s2.addText("Values = % preference for surface-rich email (S+C- vs S-C+ dissociation pair)\n>50% = surface-dominant   <50% = content-dominant   Chance = 50%", { x: 0.6, y: 4.45, w: 4.5, h: 0.4, fontSize: 9, fontFace: "Calibri", color: GRAY, italic: true });
// Key findings on right
bodyBox(s2, 5.4, 1.8, 4.0, 3.0,
  "KEY FINDINGS\n\n▸ 2 of 4 judges show statistically\n  significant surface preference\n  (GPT-4.1-mini p<0.001, Gemini p<0.001)\n\n▸ Surface decoration masks\n  content quality\n\n▸ Cross-family agreement is\n  NOT a validity signal\n\n▸ SURF provides first controlled\n  2×2 dissociation protocol",
  { fontSize: 12, bold: false });

// ══════════════════════════════════════════════
// SLIDE 3 — MOTIVATION
// ══════════════════════════════════════════════
const s3 = pres.addSlide();
bg(s3, WHITE);
titleBar(s3, "From Audit to Attack");
subtitle(s3, "SURF reveals the evaluation gap — TKG exploits it");

// Left: SURF
bodyBox(s3, 0.4, 1.7, 4.0, 1.0, "SURF AUDIT PIPELINE\nGeneration → Evaluation → Diagnosis", { fontSize: 13, bold: true });
s3.addText("Proved LLM judges are surface-biased\nContent-rich emails get misranked", { x: 0.6, y: 2.8, w: 3.6, h: 0.8, fontSize: 11, fontFace: "Calibri", color: GRAY });

// Center arrow
s3.addText("→", { x: 4.5, y: 2.0, w: 1.0, h: 0.8, fontSize: 40, color: ACCENT, align: "center", valign: "middle", bold: true });
s3.addText("SURF reveals\nthe gap", { x: 4.3, y: 2.8, w: 1.4, h: 0.7, fontSize: 10, fontFace: "Calibri", color: GRAY, align: "center" });

// Right: TKG
bodyBox(s3, 5.6, 1.7, 4.0, 1.0, "TKG ATTACK PIPELINE\nPersonas → KG → Email Gen → Human Validation", { fontSize: 13, bold: true });
s3.addText("Exploits what LLMs miss\nPersonalized content that bypasses filters", { x: 5.8, y: 2.8, w: 3.6, h: 0.8, fontSize: 11, fontFace: "Calibri", color: GRAY });

// Bottom insight
bodyBox(s3, 1.5, 3.8, 7.0, 0.8, "THESIS ARC: SURF audits the defender → TKG arms the attacker → Combined they show the full threat surface", { fontSize: 12, bold: true });

// ══════════════════════════════════════════════
// SLIDE 4 — TKG OVERVIEW
// ══════════════════════════════════════════════
const s4 = pres.addSlide();
bg(s4, WHITE);
titleBar(s4, "TKG Architecture: Five Layers");
subtitle(s4, "End-to-end pipeline from persona data to human validation");

const layers = [
  { name: "❶ DATA COLLECTION", desc: "Public sources (Semantic Scholar, Google, DuckDuckGo) → consenting researchers" },
  { name: "❷ GRAPH CONSTRUCTION", desc: "Entity extraction → nodes + edges → temporal knowledge graph" },
  { name: "❸ FEATURE EXTRACTION", desc: "Research hooks, co-authors, institutions, funding, temporal relevance" },
  { name: "❹ EMAIL GENERATION", desc: "3 conditions: Baseline, Static PII, Temporal KG → LLM generation" },
  { name: "❺ HUMAN VALIDATION", desc: "60-90 participants, partial deception, click-through measurement" },
];

let ly = 1.6;
layers.forEach((l, i) => {
  s4.addShape(pres.ShapeType.roundRect, { x: 1.5, y: ly, w: 7.0, h: 0.62, fill: { color: i === 1 || i === 2 ? NAVY : (i === 4 ? ACCENT : ICE) }, rectRadius: 0.08 });
  s4.addText(l.name, { x: 1.7, y: ly + 0.05, w: 2.5, h: 0.3, fontSize: 13, fontFace: "Calibri", bold: true, color: i === 1 || i === 2 ? WHITE : (i === 4 ? WHITE : NAVY) });
  s4.addText(l.desc, { x: 1.7, y: ly + 0.32, w: 6.5, h: 0.25, fontSize: 10, fontFace: "Calibri", color: i === 1 || i === 2 ? ICE : (i === 4 ? WHITE : DARK) });
  if (i < 4) s4.addText("▼", { x: 4.8, y: ly + 0.62, w: 0.5, h: 0.3, fontSize: 14, color: GRAY, align: "center" });
  ly += 0.72;
});

// ══════════════════════════════════════════════
// SLIDE 5 — GRAPH CONSTRUCTION Part 1
// ══════════════════════════════════════════════
const s5 = pres.addSlide();
bg(s5, WHITE);
titleBar(s5, "Building the Knowledge Graph");
subtitle(s5, "From raw persona data to structured entity-relationship graph");

// Entity boxes
const entities = [
  { name: "Person", x: 0.6, y: 2.0 },
  { name: "Paper", x: 3.5, y: 1.7 },
  { name: "Institution", x: 3.5, y: 3.3 },
  { name: "Funding", x: 6.5, y: 1.7 },
  { name: "Co-Author", x: 6.5, y: 3.3 },
];
entities.forEach(e => {
  s5.addShape(pres.ShapeType.roundRect, { x: e.x, y: e.y, w: 1.6, h: 0.7, fill: { color: NAVY }, rectRadius: 0.1 });
  s5.addText(e.name, { x: e.x, y: e.y, w: 1.6, h: 0.7, fontSize: 14, fontFace: "Calibri", bold: true, color: WHITE, align: "center", valign: "middle" });
});

// Edges (simplified as text with arrows)
const edges = [
  { from: 2.2, to: 3.5, y: 2.15, label: "authored" },
  { from: 2.2, to: 3.5, y: 3.65, label: "affiliated" },
  { from: 5.1, to: 6.5, y: 2.05, label: "funded by" },
  { from: 5.1, to: 6.5, y: 3.65, label: "collaborated" },
];
edges.forEach(e => {
  s5.addText("→", { x: e.from, y: e.y, w: 1.3, h: 0.4, fontSize: 18, color: ACCENT, align: "center" });
  s5.addText(e.label, { x: e.from, y: e.y + 0.35, w: 1.3, h: 0.3, fontSize: 9, fontFace: "Calibri", color: GRAY, align: "center", italic: true });
});

// Source
s5.addShape(pres.ShapeType.roundRect, { x: 0.6, y: 4.2, w: 8.8, h: 0.5, fill: { color: ICE } });
s5.addText("SOURCES: Semantic Scholar · Google Search + Grounding · DuckDuckGo · Open social media   |   OUTPUT: Structured KG per participant", { x: 0.8, y: 4.25, w: 8.4, h: 0.4, fontSize: 10, fontFace: "Calibri", color: DARK });

// ══════════════════════════════════════════════
// SLIDE 6 — TEMPORAL DYNAMICS
// ══════════════════════════════════════════════
const s6 = pres.addSlide();
bg(s6, WHITE);
titleBar(s6, "Temporal Dynamics");
subtitle(s6, "The Knowledge Graph is NOT static — it evolves with time");

// Timeline
const timeline = [
  { year: "2022", papers: 1 },
  { year: "2023", papers: 2 },
  { year: "2024", papers: 3 },
  { year: "2025", papers: 4 },
  { year: "2026", papers: 3 },
];
const barBaseY = 5.0;
timeline.forEach((t, i) => {
  const x = 1.0 + i * 1.8;
  const h = t.papers * 0.12;
  const barTop = barBaseY - h;
  s6.addShape(pres.ShapeType.rect, { x, y: barTop, w: 0.7, h, fill: { color: i >= 3 ? ACCENT : NAVY } });
  // Year label below bar
  s6.addText(t.year, { x: x - 0.05, y: barBaseY + 0.02, w: 0.9, h: 0.22, fontSize: 10, fontFace: "Calibri", bold: true, color: DARK, align: "center" });
  // Papers count above bar
  s6.addText(`${t.papers} papers`, { x: x - 0.05, y: barTop - 0.18, w: 0.9, h: 0.18, fontSize: 8, fontFace: "Calibri", color: i >= 3 ? ACCENT : NAVY, align: "center" });
});

// Why temporal
bodyBox(s6, 1.5, 2.0, 7.0, 1.2,
  "WHY TEMPORAL MATTERS\n\n▸ A phishing email referencing a 2022 paper is less convincing than\n  one referencing a 2025 preprint — recency = credibility\n\n▸ Collaborations change: co-authors from 3 years ago vs current lab members\n\n▸ Funding cycles: active grants more compelling than expired ones",
  { fontSize: 11 });

// ══════════════════════════════════════════════
// SLIDE 7 — FEATURE EXTRACTION Part 1
// ══════════════════════════════════════════════
const s7 = pres.addSlide();
bg(s7, WHITE);
titleBar(s7, "Personalization Features from KG");
subtitle(s7, "Five feature categories extracted from the knowledge graph");

const features = [
  { icon: "📄", name: "Research Hooks", source: "Paper nodes", example: "Your 2025 CVPR paper on adversarial robustness" },
  { icon: "👥", name: "Co-Author Networks", source: "Co-Author edges", example: "Joint work with Dr. Smith at Stanford" },
  { icon: "🏛", name: "Institutional Context", source: "Institution nodes", example: "As part of the NLP Lab at HIT" },
  { icon: "💰", name: "Funding", source: "Funding nodes", example: "Your ISF Grant #1234 on ML security" },
  { icon: "⏱", name: "Temporal Relevance", source: "Year attributes", example: "References to your most recent (2025) work" },
];

let fy = 1.6;
features.forEach(f => {
  s7.addShape(pres.ShapeType.roundRect, { x: 0.6, y: fy, w: 8.8, h: 0.62, fill: { color: fy % 2 === 0 ? ICE : WHITE }, rectRadius: 0.06 });
  s7.addText(f.icon, { x: 0.7, y: fy + 0.08, w: 0.4, h: 0.45, fontSize: 20 });
  s7.addText(f.name, { x: 1.2, y: fy + 0.03, w: 1.8, h: 0.3, fontSize: 13, fontFace: "Calibri", bold: true, color: NAVY });
  s7.addText(f.source, { x: 1.2, y: fy + 0.31, w: 1.8, h: 0.25, fontSize: 9, fontFace: "Calibri", color: GRAY, italic: true });
  s7.addText(f.example, { x: 3.2, y: fy + 0.15, w: 6.0, h: 0.3, fontSize: 11, fontFace: "Calibri", color: DARK });
  fy += 0.7;
});

// ══════════════════════════════════════════════
// SLIDE 8 — FEATURE EXTRACTION Part 2
// ══════════════════════════════════════════════
const s8 = pres.addSlide();
bg(s8, WHITE);
titleBar(s8, "Why These Features Matter");
subtitle(s8, "NIST Phish Scale: premise alignment is the #1 difficulty factor");

// Generic email
bodyBox(s8, 0.6, 1.7, 4.2, 2.5, "GENERIC EMAIL (Low Alignment)\n\n\"Dear Researcher,\n\nWe invite you to submit to the\nInternational Conference on...\"\n\n▸ No personal references\n▸ Template greeting\n▸ Generic conference name\n▸ No co-author mentions", { fontSize: 11 });
s8.addText("✗ Low premise alignment", { x: 0.8, y: 4.1, w: 3.8, h: 0.3, fontSize: 12, fontFace: "Calibri", color: ACCENT, bold: true });

// TKG email
bodyBox(s8, 5.2, 1.7, 4.2, 2.5, "TKG EMAIL (High Alignment)\n\n\"Dear Dr. Cohen,\n\nYour recent CVPR 2025 paper with\nDr. Smith on adversarial robustness\nis directly relevant to...\"\n\n▸ Real paper title + venue\n▸ Named co-author\n▸ Specific research area\n▸ Recent publication", { fontSize: 11 });
s8.addText("✓ High premise alignment", { x: 5.4, y: 4.1, w: 3.8, h: 0.3, fontSize: 12, fontFace: "Calibri", color: NAVY, bold: true });

s8.addText("Heiding et al. (2024): Personalized emails achieve 4× higher click-through rates than generic templates", { x: 0.6, y: 4.6, w: 8.8, h: 0.4, fontSize: 11, fontFace: "Calibri", color: GRAY, italic: true });

// ══════════════════════════════════════════════
// SLIDE 9 — DATA LAYER
// ══════════════════════════════════════════════
const s9 = pres.addSlide();
bg(s9, WHITE);
titleBar(s9, "Participant Recruitment & Data Collection");
subtitle(s9, "Real consenting researchers, public data only, cross-institutional recruitment");

// Left: Recruitment
bodyBox(s9, 0.6, 1.7, 4.2, 2.0,
  "PARTICIPANTS\n\n▸ 60–90 consenting researchers\n▸ CS faculty & active researchers\n▸ Published in 2024–2026 venues\n▸ Cross-institutional (HIT + Ariel)\n▸ Signed informed consent (IRB approved)\n▸ Can withdraw + delete data anytime",
  { fontSize: 11 });

// Right: Data Sources
bodyBox(s9, 5.2, 1.7, 4.2, 2.0,
  "PUBLIC DATA SOURCES ONLY\n\n▸ Semantic Scholar (publications)\n▸ Google Search with Grounding\n▸ DuckDuckGo (public profiles)\n▸ Open social media\n▸ NO password-protected accounts\n▸ NO private groups or messages",
  { fontSize: 11 });

// Bottom: Ethics
bodyBox(s9, 0.6, 4.0, 8.8, 1.2,
  "ETHICS & PRIVACY\n\n▸ IRB approved (HIT Ethics Committee)    ▸ Recruitment: cross-institutional to avoid hierarchical pressure\n▸ Informed consent with full disclosure of phishing nature    ▸ Encrypted storage, data deleted on request\n▸ Partial deception justified: participants know it's a phishing study, only timing concealed    ▸ Full debriefing after experiment",
  { fontSize: 11 });

// ══════════════════════════════════════════════
// SLIDE 10 — EMAIL GENERATION
// ══════════════════════════════════════════════
const s10 = pres.addSlide();
bg(s10, WHITE);
titleBar(s10, "Three Experimental Conditions");
subtitle(s10, "Within-subjects design: each participant receives up to 3 phishing emails");

// Condition 1
bodyBox(s10, 0.4, 1.6, 3.0, 1.5,
  "❶ BASELINE\n\nGeneric phishing email\nNo personalization\n\n\"Dear Researcher,\nyou are invited to submit\nto the conference...\"\n\n→ Minimal expected click rate",
  { fontSize: 11 });
// Condition 2
bodyBox(s10, 3.6, 1.6, 3.0, 1.5,
  "❷ STATIC PII\n\nName + Institution only\nBasic personalization\n\n\"Dear Dr. Cohen,\nStanford CS invites you\nto submit...\"\n\n→ Moderate expected click rate",
  { fontSize: 11 });
// Condition 3
bodyBox(s10, 6.8, 1.6, 3.0, 1.5,
  "❸ TEMPORAL KG (TKG)\n\nFull knowledge graph\nDeep personalization\n\n\"Your CVPR 2025 paper with\nDr. Smith on adversarial\nrobustness is...\"\n\n→ Highest expected click rate",
  { fontSize: 11 });

// Bottom: Flow
bodyBox(s10, 0.6, 3.4, 8.8, 1.8,
  "HYPOTHESES (IRB Approved)\n\nH1: Click rate(Temporal KG) > Click rate(Static PII) > Click rate(Baseline)\nH2: LLM persuasiveness scores correlate positively with actual human click rates\n    → If validated: LLM judges can serve as proxy for human risk (no future deception needed)\n\nFLOW: Public data → LLM agents build KG → GPT-4.1 generates email → Custom link token → Click tracked anonymously",
  { fontSize: 11 });

// ══════════════════════════════════════════════
// SLIDE 11 — HUMAN VALIDATION
// ══════════════════════════════════════════════
const s11 = pres.addSlide();
bg(s11, WHITE);
titleBar(s11, "Experiment Design: Measuring Real Click-Through");
s11.addText("IRB-approved behavioral experiment with partial deception", { x: 0.6, y: 1.1, w: 8.8, h: 0.35, fontSize: 13, fontFace: "Calibri", color: GRAY });

// Left: Design
bodyBox(s11, 0.6, 1.6, 4.2, 1.6,
  "DESIGN (Within-Subjects)\n\n▸ 60–90 consenting CS researchers\n▸ Each receives up to 3 phishing emails\n  (Baseline / Static PII / Temporal KG)\n▸ Custom link tokens per email\n▸ Click = yes/no + timestamp only\n▸ Partial deception: participants know\n  it's phishing study, timing concealed",
  { fontSize: 11 });

// Right: Timeline
bodyBox(s11, 5.2, 1.6, 4.2, 1.6,
  "TIMELINE (~3 months)\n\n▸ Recruitment + consent: 2 weeks\n▸ KG construction: 2 weeks\n▸ Email generation: 1 week\n▸ Sending window: 4–6 weeks\n▸ Click data collection: 1–2 weeks\n▸ Debriefing: Day 1 after close\n  (full disclosure + delete option)",
  { fontSize: 11 });

// Bottom
bodyBox(s11, 0.6, 3.5, 4.2, 1.6,
  "STATISTICAL ANALYSIS\n\n▸ McNemar / Cochran's Q\n  (dichotomous: click yes/no)\n▸ Mixed-effects logistic regression\n  (if multivariate needed)\n▸ Spearman correlation:\n  LLM scores vs human click rates",
  { fontSize: 11 });
bodyBox(s11, 5.2, 3.5, 4.2, 1.6,
  "RISK MITIGATION\n\n▸ Encrypted data, researcher-only access\n▸ Click data separated from identities\n▸ Publication: aggregate + anonymous only\n▸ Raw data destroyed within 5 years\n▸ Deception justified: essential for\n  ecological validity of click measurement",
  { fontSize: 11 });

// ══════════════════════════════════════════════
// SLIDE 12 — SURF RESULTS
// ══════════════════════════════════════════════
const s12 = pres.addSlide();
bg(s12, WHITE);
titleBar(s12, "What We Learned from SURF");
subtitle(s12, "Key findings from the CCNC 2026 paper inform the TKG design");

const findings12 = [
  { num: "1", title: "Pairwise Preference is Surface-Biased", body: "2 of 4 judges (GPT-4.1-mini, Gemini) show\nstatistically significant surface preference (p<0.001)\non the primary dissociation pair.\nSurface decoration masks content quality." },
  { num: "2", title: "Self-Contradiction", body: "Gemini contradicts own ratings on 49% of\ntrials. Comparison format activates\nsurface-driven criteria over content." },
  { num: "3", title: "Surface Stripping Recovers Content", body: "Word-count manipulation shows bias is\nmultidimensional. Stripping named entities and\nflattening formatting restores content\ndiscrimination across all 4 judges." },
];

findings12.forEach((f, i) => {
  const x = 0.4 + i * 3.2;
  s12.addShape(pres.ShapeType.roundRect, { x, y: 1.7, w: 2.9, h: 2.8, fill: { color: WHITE }, shadow: { type: "outer", blur: 6, offset: 2, color: "000000", opacity: 0.08 }, rectRadius: 0.12 });
  s12.addShape(pres.ShapeType.ellipse, { x: x + 1.0, y: 1.85, w: 0.9, h: 0.9, fill: { color: ACCENT } });
  s12.addText(f.num, { x: x + 1.0, y: 1.85, w: 0.9, h: 0.9, fontSize: 28, fontFace: "Cambria", bold: true, color: WHITE, align: "center", valign: "middle" });
  s12.addText(f.title, { x: x + 0.15, y: 2.95, w: 2.6, h: 0.4, fontSize: 14, fontFace: "Calibri", bold: true, color: NAVY, align: "center" });
  s12.addText(f.body, { x: x + 0.15, y: 3.35, w: 2.6, h: 1.0, fontSize: 10, fontFace: "Calibri", color: DARK, align: "center", lineSpacingMultiple: 1.3 });
});

s12.addText("→ Implication: Unaudited LLM judges will misrank TKG's personalized (content-rich) emails\n   lower than surface-rich generic ones. TKG exploits what SURF proved LLMs miss.", { x: 0.6, y: 4.75, w: 8.8, h: 0.5, fontSize: 11, fontFace: "Calibri", bold: true, color: ACCENT });

// ══════════════════════════════════════════════
// SLIDE 13 — THESIS ARCHITECTURE
// ══════════════════════════════════════════════
const s13 = pres.addSlide();
bg(s13, WHITE);
titleBar(s13, "From Papers to Thesis");
subtitle(s13, "Combining SURF + TKG into a cohesive thesis");

const cols = [
  { title: "SURF Paper", venue: "CCNC 2026", pages: "6 pages", desc: "LLM-as-Judge audit\n2×2 dissociation protocol\n4 judges, 100 personas\nProved surface bias", color: NAVY },
  { title: "TKG Paper", venue: "Target Journal", pages: "8-10 pages", desc: "Knowledge graph methodology\nFeature extraction pipeline\nHuman-subject validation\nDynamic temporal KG", color: ACCENT },
  { title: "Thesis", venue: "M.Sc. Thesis", pages: "Oct 2026", desc: "SURF as Chapter 2\nTKG as Chapter 3\nFuture work chapter\nCombined contribution", color: "028090" },
];
cols.forEach((c, i) => {
  const x = 0.4 + i * 3.2;
  s13.addShape(pres.ShapeType.roundRect, { x, y: 1.7, w: 2.9, h: 3.2, fill: { color: WHITE }, shadow: { type: "outer", blur: 6, offset: 2, color: "000000", opacity: 0.08 }, rectRadius: 0.12 });
  s13.addShape(pres.ShapeType.rect, { x, y: 1.7, w: 2.9, h: 0.6, fill: { color: c.color }, rectRadius: 0.0 });
  s13.addText(c.title, { x, y: 1.75, w: 2.9, h: 0.5, fontSize: 16, fontFace: "Cambria", bold: true, color: WHITE, align: "center" });
  s13.addText(`${c.venue}\n${c.pages}`, { x, y: 2.45, w: 2.9, h: 0.6, fontSize: 10, fontFace: "Calibri", color: GRAY, align: "center" });
  s13.addText(c.desc, { x: x + 0.2, y: 3.2, w: 2.5, h: 1.5, fontSize: 11, fontFace: "Calibri", color: DARK, lineSpacingMultiple: 1.5 });
  if (i < 2) s13.addText("→", { x: x + 3.0, y: 2.8, w: 0.4, h: 0.6, fontSize: 24, color: ACCENT, align: "center" });
});

// ══════════════════════════════════════════════
// SLIDE 14 — NEXT STEPS
// ══════════════════════════════════════════════
const s14 = pres.addSlide();
bg(s14, WHITE);
titleBar(s14, "10-Day Sprint + Journal Plan");
subtitle(s14, "Immediate actions and long-term publication strategy");

const phases = [
  { week: "THIS WEEK", color: ACCENT, items: ["Finalize TKG methodology document", "Get advisor feedback on KG design", "Ethics approval preparation", "Align on feature set with Florian"] },
  { week: "NEXT WEEK", color: NAVY, items: ["Pilot experiment design", "Prompt templates for email generation", "Start writing TKG paper", "IRB submission"] },
  { week: "AUGUST+", color: "028090", items: ["Run human-subject experiment", "Analyze results", "Complete TKG paper draft", "Journal selection and submission"] },
];
phases.forEach((p, i) => {
  const x = 0.4 + i * 3.2;
  s14.addShape(pres.ShapeType.roundRect, { x, y: 1.7, w: 2.9, h: 0.45, fill: { color: p.color }, rectRadius: 0.08 });
  s14.addText(p.week, { x, y: 1.7, w: 2.9, h: 0.45, fontSize: 13, fontFace: "Calibri", bold: true, color: WHITE, align: "center", valign: "middle" });
  s14.addText(p.items.join("\n"), { x: x + 0.15, y: 2.3, w: 2.6, h: 2.2, fontSize: 11, fontFace: "Calibri", color: DARK, lineSpacingMultiple: 1.6 });
});

bodyBox(s14, 0.6, 4.5, 8.8, 0.7, "KEY DEPENDENCIES: Florian's feedback on KG design · IRB approval timeline · Journal selection (no deadline, target good venue)", { fontSize: 11, bold: true });

// ══════════════════════════════════════════════
// SLIDE 15 — THANK YOU / DISCUSSION
// ══════════════════════════════════════════════
const s15 = pres.addSlide();
bg(s15, NAVY);
s15.addText("Thank You\nQuestions & Discussion", { x: 0.6, y: 0.8, w: 8.8, h: 1.4, fontSize: 36, fontFace: "Cambria", bold: true, color: WHITE, lineSpacingMultiple: 1.2 });
s15.addShape(pres.ShapeType.rect, { x: 0.6, y: 2.3, w: 2.5, h: 0.04, fill: { color: ACCENT } });

const questions = [
  "1. KG architecture — missing entities or relationships?",
  "2. Feature set — anything overlooked for personalization?",
  "3. Experiment design — validity concerns?",
  "4. Journal recommendations?",
];
questions.forEach((q, i) => {
  s15.addText(q, { x: 0.6, y: 2.6 + i * 0.45, w: 8.8, h: 0.4, fontSize: 14, fontFace: "Calibri", color: ICE });
});

s15.addText("Aviv Elbaz · Revital Marbel · Harel Berger · Florian Alt\nHIT · Ariel University · LMU Munich", { x: 0.6, y: 4.8, w: 8.8, h: 0.6, fontSize: 12, fontFace: "Calibri", color: GRAY });

// ── SAVE ──
pres.writeFile({ fileName: "/mnt/data/git/spear-phishing-llm/TKG_SURF_Presentation.pptx" }).then(() => {
  console.log("✓ Saved TKG_SURF_Presentation.pptx");
});
