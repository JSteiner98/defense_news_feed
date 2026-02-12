import feedparser
import os
import time
import json
import smtplib
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

client = genai.Client(api_key=api_key)

# 2. Define Feeds (You can add more later!)
rss_urls = ["https://warontherocks.com/feed/"]

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

def send_email(articles):
    """Formats and sends the email."""
    if not articles:
        print("No high-relevance articles found today.")
        return

    print(f"Preparing email with {len(articles)} articles...")
    
    # Create HTML Email Body
    html_content = "<h2>🛡️ Daily Defense Tech Brief</h2><hr>"
    
    for item in articles:
        html_content += f"""
        <h3>[{item['score']}/10] <a href="{item['link']}">{item['title']}</a></h3>
        <p><i>{item['category']}</i></p>
        <p>{item['summary']}</p>
        <br>
        """
    
    msg = MIMEMultipart()
    msg['From'] = email_user
    msg['To'] = email_user
    msg['Subject'] = f"Defense Brief: {len(articles)} New Articles"
    msg.attach(MIMEText(html_content, 'html'))

    try:
        # Connect to Gmail Server
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(email_user, email_pass)
        server.send_message(msg)
        server.quit()
        print("✅ Email sent successfully!")
    except Exception as e:
        print(f"❌ Email failed: {e}")

# --- MAIN EXECUTION ---
print("🚀 Starting Daily Brief...")
todays_top_picks = []

for url in rss_urls:
    feed = feedparser.parse(url)
    print(f"Scanning {len(feed.entries)} articles from {url}...")
    
    # Check top 5 articles
    for entry in feed.entries[:5]:
        print(f"Analyzing: {entry.title[:30]}...")
        
        analysis = analyze_article(entry.title, entry.summary[:1000])
        
        if analysis:
            # FILTER: Only keep if score is 7 or higher
            if analysis['score'] >= 7:
                print(f"   >>> HIT! Score {analysis['score']}/10")
                todays_top_picks.append({
                    "title": entry.title,
                    "link": entry.link,
                    "score": analysis['score'],
                    "summary": analysis['summary'],
                    "category": analysis['category']
                })
            else:
                print(f"   ...Skipping (Score {analysis['score']})")
        
        time.sleep(1.5) # Polite pause

# Send the digest
send_email(todays_top_picks)