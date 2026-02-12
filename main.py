import feedparser
import os
import time
import json
import smtplib
import requests
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google import genai
from google.genai import types
from dotenv import load_dotenv

# 1. Load Secrets
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
email_user = os.getenv("EMAIL_ADDRESS")
email_pass = os.getenv("EMAIL_PASSWORD")
sam_api_key = os.getenv("SAM_GOV_API_KEY")

client = genai.Client(api_key=api_key)

# 2. Configuration
ENTRIES_PER_FEED = 3    # articles to check per feed (kept low to manage API calls across 9 feeds)
API_DELAY = 1.0         # seconds between Gemini calls
RELEVANCE_THRESHOLD = 7 # minimum score (0-10) to include in digest

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


def analyze_article(title, snippet):
    """Sends article to AI and returns a clean JSON object."""
    prompt = f"""
    You are a defense tech analyst for a Venture Capital firm. 
    Analyze this article. Return ONLY a JSON object with these fields:
    - "score": A number 0-10 based on relevance to "Maritime Defense", "American Dynamism" (Anduril-style tech), or "AI Hardware".
    - "summary": A 2-sentence executive summary.
    - "category": Choose one: "Maritime", "AI/Tech", "Geopolitics", "Other".

    Article: {title}
    Snippet: {snippet}
    """
    
    try:
        # We ask Gemini specifically for JSON response
        response = client.models.generate_content(
            model='gemini-flash-latest',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type='application/json'
            )
        )
        return json.loads(response.text)
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

# --- MAIN EXECUTION ---
print("Starting Daily Brief...")
todays_top_picks: list[dict] = []

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
            print(f"  Analyzing: {title[:50]}...")

            analysis = analyze_article(title, snippet)
            if analysis and analysis.get("score", 0) >= RELEVANCE_THRESHOLD:
                print(f"    >>> HIT! Score {analysis['score']}/10")
                todays_top_picks.append({
                    "title": title,
                    "link": getattr(entry, "link", ""),
                    "score": analysis["score"],
                    "summary": analysis["summary"],
                    "category": analysis["category"],
                    "source": feed_name,
                })
            elif analysis:
                print(f"    ...Skipping (Score {analysis.get('score', '?')})")

            time.sleep(API_DELAY)

# Phase 2: SAM.gov Contract Opportunities
scored_opportunities: list[dict] = []
if sam_api_key:
    print("\n--- SAM.gov Contracts ---")
    raw_opps = fetch_sam_opportunities(sam_api_key)
    for opp in raw_opps:
        print(f"  Scoring: {opp['title'][:50]}...")
        analysis = analyze_article(opp["title"], opp.get("solicitationNumber", ""))
        if analysis and analysis.get("score", 0) >= RELEVANCE_THRESHOLD:
            print(f"    >>> HIT! Score {analysis['score']}/10")
            scored_opportunities.append({**opp, **analysis})
        elif analysis:
            print(f"    ...Skipping (Score {analysis.get('score', '?')})")
        time.sleep(API_DELAY)
else:
    print("\nSAM_GOV_API_KEY not set — skipping contract opportunities.")

# Phase 3: Send combined digest
send_email(todays_top_picks, scored_opportunities)