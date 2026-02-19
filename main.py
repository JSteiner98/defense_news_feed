import feedparser
import os
import json
import re

import smtplib
import requests
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# 1. Load Secrets
load_dotenv()
email_user = os.getenv("EMAIL_ADDRESS")
email_pass = os.getenv("EMAIL_PASSWORD")
sam_api_key = os.getenv("SAM_GOV_API_KEY")

# 2. Configuration
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"
ENTRIES_PER_FEED = 3    # articles to check per feed
RELEVANCE_THRESHOLD = 4 # minimum composite score (0-10) to include in digest

KEYWORD_TIERS: dict[str, int] = {
    # Tier 1 (weight 3) — highly specific, almost always means relevance
    "Anduril": 3,
    "Jones Act": 3,
    "Section 27": 3,
    "Sealift": 3,
    "Maritime Autonomy": 3,
    "Dive-LD": 3,
    "Ghost Shark": 3,
    "Saronic": 3,
    "Saildrone": 3,
    "Shield AI": 3,
    "Palantir": 3,
    "Replicator Initiative": 3,
    "Maritime Action Plan": 3,
    "MAP": 3,
    "USV": 3,
    "UUV": 3,
    "CCA": 3,
    "MASC": 3,
    "Lattice OS": 3,
    "Hivemind": 3,
    "Hedge Strategy": 3,
    # Tier 2 (weight 2) — relevant but sometimes ambiguous
    "MSC": 2,
    "unmanned systems": 2,
    "defense AI": 2,
    "autonomous vessels": 2,
    "Maritime Domain Awareness": 2,
    "MDA": 2,
    "Attritable": 2,
    "Low-cost": 2,
    "DIU": 2,
    "Defense Innovation Unit": 2,
    "Distributed Maritime Operations": 2,
    "DMO": 2,
    "Physical AI": 2,
    "Autonomous Welding": 2,
    "ISR": 2,
    "Intelligence, Surveillance, Reconnaissance": 2,
    # Tier 3 (weight 1) — broad, adds context but not definitive alone
    "autonomous": 1,
    "semi-autonomous": 1,
    "naval": 1,
    "Coast Guard": 1,
    "shipbuilding": 1,
    "shipyard": 1,
    "readiness": 1,
    "dual-use": 1,
    "supply chain": 1,
}

TITLE_MULTIPLIER = 2  # keyword matches in the title count double

RSS_FEEDS = {
    "Defense": [
        ("War on the Rocks", "https://warontherocks.com/feed/"),
        ("Defense One - Tech", "https://www.defenseone.com/rss/technology"),
        ("Breaking Defense", "https://breakingdefense.com/full-rss-feed/"),
        ("Defense News", "https://www.defensenews.com/m/rss/"),
        ("USNI News", "https://news.usni.org/feed"),
    ],
    "Maritime": [
        ("gCaptain", "https://feeds.feedburner.com/gcaptain"),
        ("Maritime Executive", "https://maritime-executive.com/rss"),
    ],
    "Tech": [
        ("Wired Security", "https://www.wired.com/feed/category/security"),
    ],
    "Government": [
        ("Federal News Network", "https://federalnewsnetwork.com/feed"),
    ],
}

def get_entry_snippet(entry: feedparser.FeedParserDict) -> str:
    """Safely extracts text from an RSS entry regardless of feed structure.

    Different feeds store article text in different fields — some use 'summary',
    others use 'content' (a list), and some fall back to 'description'. This
    helper checks each option so we don't crash on unfamiliar feeds.
    """
    # 'content' is a list of dicts in some Atom feeds; grab the first one's value
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].get("value", "")[:1000]
    # Most RSS 2.0 feeds use 'summary'
    if hasattr(entry, "summary") and entry.summary:
        return entry.summary[:1000]
    # Last resort
    if hasattr(entry, "description") and entry.description:
        return entry.description[:1000]
    return ""


def scan_keywords(title: str, snippet: str) -> dict:
    """Deterministic keyword scan that scores based on weighted tier matches.

    Uses regex word boundaries (\\b) so "MSC" won't match inside "MSCellaneous".
    Title matches count double (TITLE_MULTIPLIER) because a keyword in the title
    is a much stronger relevance signal than one buried in body text.

    Returns a dict with:
      - keyword_score: float 0-10 (raw points normalized via min(10, raw / 6 * 10))
      - matched_keywords: list of dicts for logging (keyword, weight, location)
    """
    matched_keywords: list[dict] = []
    raw_points = 0

    for keyword, weight in KEYWORD_TIERS.items():
        pattern = re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)

        if pattern.search(title):
            points = weight * TITLE_MULTIPLIER
            raw_points += points
            matched_keywords.append({
                "keyword": keyword,
                "weight": weight,
                "location": "title",
            })
        elif pattern.search(snippet):
            raw_points += weight
            matched_keywords.append({
                "keyword": keyword,
                "weight": weight,
                "location": "snippet",
            })

    keyword_score = min(10, raw_points / 6 * 10)
    return {"keyword_score": round(keyword_score, 1), "matched_keywords": matched_keywords}


def compute_composite_score(llm_score: int, keyword_score: float) -> int:
    """Combines the LLM score (60%) with the keyword score (40%) into a 0-10 int.

    The 60/40 split means the LLM still dominates — it understands context that
    keywords can't capture — but a strong keyword match provides a reliable floor.
    An article mentioning "Anduril" in the title can never score below 4, even if
    the LLM gives it a 0.
    """
    return min(10, round((llm_score * 0.6) + (keyword_score * 0.4)))


def fetch_sam_opportunities(api_key: str) -> list[dict]:
    """Fetches recent contract opportunities from SAM.gov relevant to defense/maritime.

    Makes two searches — one by NAICS code for shipbuilding/repair, one by keyword
    for defense tech — then deduplicates results. Returns a list of opportunity dicts
    with fields: title, solicitationNumber, naicsCode, type, responseDeadLine, link.
    """
    base_url = "https://api.sam.gov/opportunities/v2/search"
    # Rolling 7-day window so we always see fresh opportunities
    date_from = (datetime.now() - timedelta(days=7)).strftime("%m/%d/%Y")
    date_to = datetime.now().strftime("%m/%d/%Y")

    searches = [
        {
            "description": "Shipbuilding & Repair (NAICS 336611)",
            "params": {
                "api_key": api_key,
                "postedFrom": date_from,
                "postedTo": date_to,
                "ncode": "336611",
                "limit": 10,
            },
        },
        {
            "description": "Defense Tech Keywords",
            "params": {
                "api_key": api_key,
                "postedFrom": date_from,
                "postedTo": date_to,
                "q": "autonomous unmanned AI robotics",
                "limit": 10,
            },
        },
    ]

    seen_ids: set[str] = set()
    opportunities: list[dict] = []

    for search in searches:
        print(f"  SAM.gov: Searching {search['description']}...")
        try:
            resp = requests.get(base_url, params=search["params"], timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  SAM.gov Error ({search['description']}): {e}")
            continue

        for opp in data.get("opportunitiesData", []):
            notice_id = opp.get("noticeId", "")
            if notice_id in seen_ids:
                continue
            seen_ids.add(notice_id)

            opportunities.append({
                "title": opp.get("title", "Untitled"),
                "solicitationNumber": opp.get("solicitationNumber", "N/A"),
                "naicsCode": opp.get("naicsCode", "N/A"),
                "type": opp.get("type", "N/A"),
                "responseDeadLine": opp.get("responseDeadLine", "N/A"),
                "link": f"https://sam.gov/opp/{notice_id}/view",
            })

    print(f"  SAM.gov: Found {len(opportunities)} unique opportunities")
    return opportunities


def analyze_article(title: str, snippet: str) -> dict | None:
    """Sends article to Ollama (local Llama 3.2) and returns a clean JSON object.

    Uses Ollama's 'format: json' option, which constrains the model to only
    output valid JSON — similar to Gemini's response_mime_type setting.
    Because the model runs locally, there are no rate limits or API keys needed.
    """
    keywords_str = ", ".join(KEYWORD_TIERS.keys())
    prompt = f"""You are a defense-tech analyst screening articles for a daily digest.
Score the article below on a 0-10 scale using this rubric:

  8-10: Directly mentions a priority keyword ({keywords_str}) OR covers
        a specific contract award, weapon-system milestone, or policy change
        in maritime defense / autonomous systems / defense AI.
        Examples: "Navy awards $400M sealift contract", "Anduril unveils
        autonomous patrol boat".
  5-7:  General defense-industry or military news that is useful background
        but does not mention priority keywords or a specific program.
        Examples: "Pentagon budget request overview", "NATO exercises in
        the Baltic".
  1-4:  Tangentially related — mentions the military but focuses on
        politics, lifestyle, or broad geopolitics with no defense-tech angle.
  0:    Completely irrelevant (sports, entertainment, etc.).

Priority keywords (boost score when present): {keywords_str}

Return ONLY a JSON object with these fields:
- "score": integer 0-10 per the rubric above
- "summary": 2-sentence executive summary
- "category": one of "Maritime", "AI/Tech", "Geopolitics", "Contracting", "Other"

Article title: {title}
Snippet: {snippet}"""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "format": "json",   # forces valid JSON output
            "stream": False,    # wait for the full response at once
        }, timeout=120)
        resp.raise_for_status()
        return json.loads(resp.json()["response"])
    except Exception as e:
        print(f"AI Error: {e}")
        return None

def analyze_sam_opportunity(opp: dict) -> dict | None:
    """Scores a SAM.gov contract opportunity using structured metadata.

    Unlike news articles, contracts have fields like NAICS code and response
    deadline that tell the model a lot about relevance. This function formats
    all of that into the prompt so scoring is based on real context — not just
    the title and a solicitation number.
    """
    keywords_str = ", ".join(KEYWORD_TIERS.keys())
    prompt = f"""You are a defense-tech analyst screening government contract opportunities.
Score this opportunity on a 0-10 scale using this rubric:

  8-10: Directly related to priority keywords ({keywords_str}) OR involves
        shipbuilding, autonomous systems, defense AI, or maritime logistics.
  5-7:  General defense/government contract that may be tangentially relevant.
  1-4:  Government contract with little defense-tech relevance.
  0:    Completely irrelevant.

Priority keywords (boost score when present): {keywords_str}

Return ONLY a JSON object with these fields:
- "score": integer 0-10 per the rubric above
- "summary": 2-sentence description of what this contract covers and why it matters
- "category": one of "Maritime", "AI/Tech", "Geopolitics", "Contracting", "Other"

Contract title: {opp.get('title', 'Untitled')}
Solicitation number: {opp.get('solicitationNumber', 'N/A')}
NAICS code: {opp.get('naicsCode', 'N/A')}
Type: {opp.get('type', 'N/A')}
Response deadline: {opp.get('responseDeadLine', 'N/A')}"""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
        }, timeout=120)
        resp.raise_for_status()
        return json.loads(resp.json()["response"])
    except Exception as e:
        print(f"AI Error: {e}")
        return None


def send_email(articles: list[dict], opportunities: list[dict]) -> None:
    """Formats and sends the digest email with news articles and contract opportunities."""
    if not articles and not opportunities:
        print("No high-relevance articles or contracts found today.")
        return

    print(f"Preparing email with {len(articles)} articles and {len(opportunities)} contracts...")

    # --- News Articles Section ---
    html_content = "<h2>Daily Defense Tech Brief</h2><hr>"

    if articles:
        html_content += "<h3>News Articles</h3>"
        for item in articles:
            html_content += f"""
            <h4>[{item['score']}/10] <a href="{item['link']}">{item['title']}</a></h4>
            <p><i>{item['category']}</i> &mdash; Source: {item.get('source', 'Unknown')}</p>
            <p>{item['summary']}</p>
            <br>
            """

    # --- Contract Opportunities Section ---
    if opportunities:
        html_content += "<hr><h3>Contract Opportunities (SAM.gov)</h3>"
        for opp in opportunities:
            html_content += f"""
            <h4>[{opp['score']}/10] <a href="{opp['link']}">{opp['title']}</a></h4>
            <p><b>Solicitation:</b> {opp['solicitationNumber']}
               &nbsp;|&nbsp; <b>NAICS:</b> {opp['naicsCode']}
               &nbsp;|&nbsp; <b>Type:</b> {opp['type']}</p>
            <p><b>Response Deadline:</b> {opp['responseDeadLine']}</p>
            <p>{opp['summary']}</p>
            <br>
            """

    msg = MIMEMultipart()
    msg['From'] = email_user
    msg['To'] = email_user
    msg['Subject'] = f"Defense Brief: {len(articles)} Articles, {len(opportunities)} Contracts"
    msg.attach(MIMEText(html_content, 'html'))

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(email_user, email_pass)
        server.send_message(msg)
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Email failed: {e}")

def save_run_log(
    all_articles: list[dict],
    all_opportunities: list[dict],
    hit_articles: list[dict],
    hit_opportunities: list[dict],
) -> None:
    """Saves a timestamped JSON log of the full run to the output/ directory.

    Logs every scored item — not just hits — so you can review what was filtered
    out and decide if the threshold or rubric needs adjusting. The summary stats
    at the top (e.g., "8 hits out of 27 scored") immediately tell you whether
    filtering is too strict or too loose.
    """
    os.makedirs("output", exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filepath = f"output/run_{timestamp}.json"

    log_data = {
        "run_timestamp": datetime.now().isoformat(),
        "config": {
            "model": OLLAMA_MODEL,
            "relevance_threshold": RELEVANCE_THRESHOLD,
            "entries_per_feed": ENTRIES_PER_FEED,
            "keyword_tiers": KEYWORD_TIERS,
            "title_multiplier": TITLE_MULTIPLIER,
        },
        "summary": {
            "articles_scored": len(all_articles),
            "articles_hits": len(hit_articles),
            "opportunities_scored": len(all_opportunities),
            "opportunities_hits": len(hit_opportunities),
        },
        "articles": all_articles,
        "opportunities": all_opportunities,
    }

    with open(filepath, "w") as f:
        json.dump(log_data, f, indent=2, default=str)

    print(f"\nRun log saved to {filepath}")


# --- MAIN EXECUTION ---
print("Starting Daily Brief...")
todays_top_picks: list[dict] = []
all_scored_articles: list[dict] = []      # every article, hit or miss — for the run log

# Phase 1: RSS Feeds — loop by category so the console output is organized
for category, feeds in RSS_FEEDS.items():
    print(f"\n--- {category} ---")
    for feed_name, feed_url in feeds:
        feed = feedparser.parse(feed_url)
        entry_count = min(len(feed.entries), ENTRIES_PER_FEED)
        print(f"Scanning {entry_count} articles from {feed_name}...")

        for entry in feed.entries[:ENTRIES_PER_FEED]:
            title = getattr(entry, "title", "Untitled")
            snippet = get_entry_snippet(entry)
            link = getattr(entry, "link", "")
            print(f"  Analyzing: {title[:50]}...")

            analysis = analyze_article(title, snippet)
            if not analysis:
                continue

            llm_score = analysis.get("score", 0)
            keyword_results = scan_keywords(title, snippet)
            composite = compute_composite_score(llm_score, keyword_results["keyword_score"])

            article_record = {
                "title": title,
                "link": link,
                "score": composite,
                "llm_score": llm_score,
                "keyword_score": keyword_results["keyword_score"],
                "matched_keywords": keyword_results["matched_keywords"],
                "summary": analysis.get("summary", "No summary available."),
                "category": analysis.get("category", "Other"),
                "source": feed_name,
            }
            all_scored_articles.append(article_record)

            if composite >= RELEVANCE_THRESHOLD:
                print(f"    >>> HIT! Score {composite}/10 (LLM={llm_score}, KW={keyword_results['keyword_score']})")
                todays_top_picks.append(article_record)
            else:
                print(f"    ...Skipping (Score {composite}/10, LLM={llm_score}, KW={keyword_results['keyword_score']})")


# Phase 2: SAM.gov Contract Opportunities
scored_opportunities: list[dict] = []
all_scored_opportunities: list[dict] = []  # every opportunity, hit or miss — for the run log
if sam_api_key:
    print("\n--- SAM.gov Contracts ---")
    raw_opps = fetch_sam_opportunities(sam_api_key)
    for opp in raw_opps:
        print(f"  Scoring: {opp['title'][:50]}...")
        analysis = analyze_sam_opportunity(opp)
        if not analysis:
            continue

        llm_score = analysis.get("score", 0)
        keyword_results = scan_keywords(opp["title"], "")
        composite = compute_composite_score(llm_score, keyword_results["keyword_score"])

        opp_record = {
            **opp,
            **analysis,
            "score": composite,
            "llm_score": llm_score,
            "keyword_score": keyword_results["keyword_score"],
            "matched_keywords": keyword_results["matched_keywords"],
        }
        all_scored_opportunities.append(opp_record)

        if composite >= RELEVANCE_THRESHOLD:
            print(f"    >>> HIT! Score {composite}/10 (LLM={llm_score}, KW={keyword_results['keyword_score']})")
            scored_opportunities.append(opp_record)
        else:
            print(f"    ...Skipping (Score {composite}/10, LLM={llm_score}, KW={keyword_results['keyword_score']})")
else:
    print("\nSAM_GOV_API_KEY not set — skipping contract opportunities.")

# Phase 3: Save run log, then send combined digest
save_run_log(all_scored_articles, all_scored_opportunities, todays_top_picks, scored_opportunities)
send_email(todays_top_picks, scored_opportunities)