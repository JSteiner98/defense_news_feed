"""
Generates a flowchart of main.py as a PNG using Graphviz.
Run:    python generate_diagram.py
Output: output/defense_brief_architecture.png
"""

import os
import graphviz

os.makedirs("output", exist_ok=True)

# ── Color palette ─────────────────────────────────────────────────────────────
C_INPUT    = "#D6E8FF"   # blue   — config / inputs
C_PROCESS  = "#DFF5E1"   # green  — processing steps
C_LLM      = "#EDE0FF"   # purple — AI / LLM steps
C_SCORE    = "#FFE8D6"   # orange — scoring / math
C_DECISION = "#FFF3CD"   # amber  — decision points
C_OUTPUT   = "#FFE0E0"   # red    — final outputs
C_MISS     = "#F0F0F0"   # grey   — filtered-out items
C_NOTE     = "#FFFDE7"   # light yellow — tuning notes / troubleshooting
C_TITLE    = "#1A1A2E"   # dark navy — title block
C_BORDER   = "#444444"
FONT       = "Helvetica"

# ── HTML label helper ─────────────────────────────────────────────────────────
def hl(title: str, subtitle: str = "") -> str:
    """Returns an HTML-style Graphviz label with a bold title and smaller subtitle."""
    if subtitle:
        return (
            f'<<B>{title}</B><BR/>'
            f'<FONT POINT-SIZE="9" COLOR="#555555">{subtitle}</FONT>>'
        )
    return f'<<B>{title}</B>>'

# ── Graph setup ───────────────────────────────────────────────────────────────
g = graphviz.Digraph(
    "defense_brief",
    format="png",
    graph_attr={
        "rankdir":  "TB",
        "nodesep":  "0.55",
        "ranksep":  "0.65",
        "bgcolor":  "#F7F9FC",
        "fontname": FONT,
        "pad":      "0.6",
        "dpi":      "180",
    },
    node_attr={
        "fontname": FONT,
        "fontsize": "11",
        "style":    "filled,rounded",
        "penwidth": "1.5",
        "color":    C_BORDER,
        "margin":   "0.18,0.12",
    },
    edge_attr={
        "fontname": FONT,
        "fontsize": "9",
        "color":    "#666666",
        "penwidth": "1.4",
        "fontcolor":"#444444",
    },
)

# ── Shorthand node/edge builders ──────────────────────────────────────────────
def box(name, title, subtitle="", color=C_PROCESS, shape="box", **kw):
    g.node(name, label=hl(title, subtitle), shape=shape,
           fillcolor=color, **kw)

def diamond(name, title, subtitle=""):
    g.node(name, label=hl(title, subtitle), shape="diamond",
           fillcolor=C_DECISION, width="2.0", height="0.9", fontsize="10")

def edge(a, b, label="", **kw):
    g.edge(a, b, label=f"  {label}  " if label else "", **kw)

def note(name: str, title: str, lines: list[str]) -> None:
    """Renders a folded-corner annotation box with a bold title and bullet lines."""
    body = "<BR/>".join(
        f'<FONT POINT-SIZE="8" COLOR="#555555">{l}</FONT>' for l in lines
    )
    label = f'<<B>{title}</B><BR/>{body}>'
    g.node(name, label=label, shape="note", style="filled", fillcolor=C_NOTE,
           fontname=FONT, fontsize="10", color="#BBAA00", penwidth="1.2")

def note_edge(a: str, b: str) -> None:
    """Dashed, arrowless edge for connecting a node to its annotation."""
    g.edge(a, b, style="dashed", color="#BBAA00", penwidth="1.0", arrowhead="none")

# ═════════════════════════════════════════════════════════════════════════════
# TITLE BLOCK
# ═════════════════════════════════════════════════════════════════════════════
g.node(
    "title",
    label=(
        '<<FONT POINT-SIZE="16" COLOR="white"><B>Defense Brief — main.py Architecture</B></FONT><BR/>'
        '<FONT POINT-SIZE="10" COLOR="#AAAACC">Automated pipeline: RSS + SAM.gov → AI scoring → Email digest</FONT>>'
    ),
    shape="box",
    style="filled,rounded",
    fillcolor=C_TITLE,
    color=C_TITLE,
    fontname=FONT,
    penwidth="0",
    margin="0.3,0.2",
)

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 1 — INGESTION
# ═════════════════════════════════════════════════════════════════════════════
with g.subgraph(name="cluster_phase1") as p1:
    p1.attr(
        label="Phase 1 — Ingestion",
        style="filled,rounded", fillcolor="#EEF4FF",
        color="#3A86FF", fontcolor="#3A86FF",
        fontsize="11", fontname=FONT,
    )
    p1.node("rss_cfg",
        label=hl("RSS Sources", "9 feeds · 4 categories"),
        shape="box", style="filled,rounded", fillcolor=C_INPUT,
        fontname=FONT, fontsize="11", color=C_BORDER, penwidth="1.5")
    p1.node("feedparser",
        label=hl("Fetch Entries", "feedparser.parse() · 3 articles per feed"),
        shape="box", style="filled,rounded", fillcolor=C_PROCESS,
        fontname=FONT, fontsize="11", color=C_BORDER, penwidth="1.5")
    p1.node("snippet",
        label=hl("Extract Text", "get_entry_snippet() · up to 1,000 chars"),
        shape="box", style="filled,rounded", fillcolor=C_PROCESS,
        fontname=FONT, fontsize="11", color=C_BORDER, penwidth="1.5")

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 2 — SCORING (two parallel lanes inside one cluster)
# ═════════════════════════════════════════════════════════════════════════════
with g.subgraph(name="cluster_scoring") as sc:
    sc.attr(
        label="Phase 2 — Scoring",
        style="filled,rounded", fillcolor="#F4FFF6",
        color="#2DC653", fontcolor="#2DC653",
        fontsize="11", fontname=FONT,
    )

    # Lane A — keyword scan
    with sc.subgraph(name="cluster_kw") as kw:
        kw.attr(
            label="2a · Keyword Scan",
            style="rounded,dashed", color="#2DC653",
            fontcolor="#2DC653", fontsize="10", fontname=FONT,
        )
        kw.node("scan_kw",
            label=hl("scan_keywords()", "Regex match · ~35 tiered keywords"),
            shape="box", style="filled,rounded", fillcolor=C_PROCESS,
            fontname=FONT, fontsize="11", color=C_BORDER, penwidth="1.5")
        kw.node("kw_norm",
            label=hl("Keyword Score", "Title hits × 2 · normalized 0–10"),
            shape="box", style="filled,rounded", fillcolor=C_PROCESS,
            fontname=FONT, fontsize="11", color=C_BORDER, penwidth="1.5")

    # Lane B — LLM
    with sc.subgraph(name="cluster_llm") as llm:
        llm.attr(
            label="2b · AI Scoring",
            style="rounded,dashed", color="#8338EC",
            fontcolor="#8338EC", fontsize="10", fontname=FONT,
        )
        llm.node("ollama",
            label=hl("Ollama (Llama 3.2)", "Local LLM · revised rubric prompt (Mar 2026)"),
            shape="box", style="filled,rounded", fillcolor=C_LLM,
            fontname=FONT, fontsize="11", color=C_BORDER, penwidth="1.5")
        llm.node("llm_resp",
            label=hl("LLM Score", "Returns score · summary · category"),
            shape="box", style="filled,rounded", fillcolor=C_LLM,
            fontname=FONT, fontsize="11", color=C_BORDER, penwidth="1.5")

    # Composite merge
    sc.node("composite",
        label=hl("Composite Score", "(LLM × 60%) + (Keywords × 40%)"),
        shape="box", style="filled,rounded", fillcolor=C_SCORE,
        fontname=FONT, fontsize="11", color=C_BORDER, penwidth="1.5")

diamond("threshold", "Score ≥ 3?", "RELEVANCE_THRESHOLD = 3 (articles)")

box("article_rec", "Article Record", "title · score · summary · category · source",
    color=C_PROCESS)
box("miss", "Filtered Out", "below threshold", color=C_MISS)

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 3 — SAM.GOV (parallel track on the right)
# ═════════════════════════════════════════════════════════════════════════════
with g.subgraph(name="cluster_sam") as sam:
    sam.attr(
        label="Phase 3 — SAM.gov Contracts",
        style="filled,rounded", fillcolor="#FFF0F8",
        color="#FF006E", fontcolor="#FF006E",
        fontsize="11", fontname=FONT,
    )
    sam.node("sam_fetch",
        label=hl("Fetch Contracts", "Shipbuilding (NAICS) + keyword search · 7-day window"),
        shape="box", style="filled,rounded", fillcolor=C_INPUT,
        fontname=FONT, fontsize="11", color=C_BORDER, penwidth="1.5")
    sam.node("sam_llm",
        label=hl("Score with AI", "Contract-specific prompt · NAICS · deadline · type"),
        shape="box", style="filled,rounded", fillcolor=C_LLM,
        fontname=FONT, fontsize="11", color=C_BORDER, penwidth="1.5")
    sam.node("sam_kw",
        label=hl("Keyword Scan", "Same KEYWORD_TIERS · same composite formula"),
        shape="box", style="filled,rounded", fillcolor=C_PROCESS,
        fontname=FONT, fontsize="11", color=C_BORDER, penwidth="1.5")

diamond("sam_thresh", "Score ≥ 7?", "CONTRACT_THRESHOLD = 7")
box("sam_hit", "Contract Record", "title · score · summary · deadline · link",
    color=C_PROCESS)

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 4 — OUTPUT
# ═════════════════════════════════════════════════════════════════════════════
with g.subgraph(name="cluster_output") as out:
    out.attr(
        label="Phase 4 — Output",
        style="filled,rounded", fillcolor="#FFF5F5",
        color="#CC2200", fontcolor="#CC2200",
        fontsize="11", fontname=FONT,
    )
    out.node("run_log",
        label=hl("Run Log", "All scored items saved to output/run_TIMESTAMP.json"),
        shape="box", style="filled,rounded", fillcolor=C_OUTPUT,
        fontname=FONT, fontsize="11", color=C_BORDER, penwidth="1.5")
    out.node("email",
        label=hl("Email Digest", "HTML email · articles + contracts · Gmail SMTP"),
        shape="box", style="filled,rounded", fillcolor=C_OUTPUT,
        fontname=FONT, fontsize="11", color=C_BORDER, penwidth="1.5")

# ═════════════════════════════════════════════════════════════════════════════
# TROUBLESHOOTING ANNOTATIONS
# ═════════════════════════════════════════════════════════════════════════════
note("note_rubric", "LLM Rubric Rewrite (Mar 2026)", [
    "Problem: old 5-7 bucket was vague ('useful background').",
    "LLM often scored good articles at 5 → composite 3.0 → filtered out.",
    "Fix: new 6-7 explicitly covers strategic policy, geopolitics w/ military-",
    "industrial angle, acquisition/budget news, shipbuilding — clear examples given.",
    "New 3-5: broad military/political, limited defense-tech signal (still passes).",
    "Also tried: Gemini API (replaced w/ local Ollama — no rate limits or costs).",
])

note("note_article_thresh", "Article Threshold History", [
    "Problem: threshold=4 killed articles with LLM=5.",
    "Math: 5 × 0.6 = 3.0 composite — below old threshold of 4.",
    "Fix: lowered to RELEVANCE_THRESHOLD=3 (Mar 2026).",
    "Future: could drop to 2 if noise increases; raise back to 4 if too broad.",
    "Also watch: TITLE_MULTIPLIER=2 boosts keyword-heavy articles significantly.",
])

note("note_contract_thresh", "Contract Threshold History", [
    "Problem: shared threshold=4 let nearly all defense contracts through.",
    "Root cause: contract prompt's 5-7 bucket ('general defense') was too broad;",
    "LLM scored most SAM.gov results at 5+ → composite 4 → passed.",
    "Fix: split to CONTRACT_THRESHOLD=7 — contracts must be specifically relevant.",
    "Future: could cap SAM search limit (currently 10/query), or add keyword",
    "pre-filter before scoring to avoid scoring clearly irrelevant items.",
])

note("note_tuning", "Scoring Tuning Levers", [
    "Composite weights: 60% LLM / 40% KW — adjust if keywords over/under-weight.",
    "KW normalization: raw ÷ 6 × 10 — lower divisor = keywords matter more.",
    "ENTRIES_PER_FEED=3 — increase to scan more articles per feed.",
    "OLLAMA_MODEL=llama3.2 — try larger model for better nuance.",
    "Future: could cache LLM scores to avoid re-scoring unchanged articles.",
])

# ═════════════════════════════════════════════════════════════════════════════
# LEGEND
# ═════════════════════════════════════════════════════════════════════════════
with g.subgraph(name="cluster_legend") as leg:
    leg.attr(
        label="Legend",
        style="filled,rounded", fillcolor="#F0F0F0",
        color="#999999", fontcolor="#666666",
        fontsize="10", fontname=FONT,
        rank="sink",
    )
    items = [
        ("leg_input",    C_INPUT,    "Config / Input"),
        ("leg_process",  C_PROCESS,  "Processing Step"),
        ("leg_llm",      C_LLM,      "AI / LLM"),
        ("leg_score",    C_SCORE,    "Scoring / Math"),
        ("leg_decision", C_DECISION, "Decision"),
        ("leg_output",   C_OUTPUT,   "Output"),
        ("leg_miss",     C_MISS,     "Filtered Out"),
        ("leg_note",     C_NOTE,     "Tuning Note"),
    ]
    prev = None
    for nid, color, label in items:
        leg.node(nid, label=f"  {label}  ", shape="box",
                 style="filled,rounded", fillcolor=color,
                 fontname=FONT, fontsize="9", color=C_BORDER, penwidth="1.0")
        if prev:
            leg.edge(prev, nid, style="invis")  # invisible edge to line them up
        prev = nid

# ═════════════════════════════════════════════════════════════════════════════
# EDGES
# ═════════════════════════════════════════════════════════════════════════════

# Title → Phase 1
edge("title",      "rss_cfg",     style="invis")   # layout anchor only
edge("title",      "sam_fetch",   style="invis")

# Phase 1 flow
edge("rss_cfg",    "feedparser")
edge("feedparser", "snippet")
edge("snippet",    "scan_kw",  label="title + text")
edge("snippet",    "ollama",   label="title + text")

# Scoring lanes
edge("scan_kw",    "kw_norm")
edge("kw_norm",    "composite", label="keyword score")
edge("ollama",     "llm_resp")
edge("llm_resp",   "composite", label="LLM score")

# Decision
edge("composite",  "threshold")
edge("threshold",  "article_rec", label="YES",
     color="#2DC653", fontcolor="#2DC653", penwidth="2.0")
edge("threshold",  "miss",        label="NO",
     color="#AAAAAA", fontcolor="#AAAAAA", style="dashed")

# SAM.gov path
edge("sam_fetch",  "sam_llm")
edge("sam_fetch",  "sam_kw")
edge("sam_llm",    "sam_thresh", label="LLM score")
edge("sam_kw",     "sam_thresh", label="keyword score")
edge("sam_thresh", "sam_hit",    label="YES",
     color="#2DC653", fontcolor="#2DC653", penwidth="2.0")

# Both hit types → output
edge("article_rec","run_log")
edge("article_rec","email")
edge("sam_hit",    "run_log")
edge("sam_hit",    "email")
edge("miss",       "run_log", style="dashed", color="#AAAAAA")

# Annotation connections
note_edge("ollama",     "note_rubric")
note_edge("threshold",  "note_article_thresh")
note_edge("sam_thresh", "note_contract_thresh")
note_edge("composite",  "note_tuning")

# ═════════════════════════════════════════════════════════════════════════════
# RENDER
# ═════════════════════════════════════════════════════════════════════════════
output_path = "output/defense_brief_architecture"
g.render(output_path, cleanup=True)
print(f"Diagram saved to {output_path}.png")
