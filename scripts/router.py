## File Name: router.py
## Description: RSS routing with per-feed progress and DuckDuckGo fallback
## Path: scripts/router.py
## Created By: Lokesh R     Created On: 2026-05-27
## Updated By: Lokesh R     Updated On: 2026-05-27

## Import - Libraries
import feedparser
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

RSS_SOURCES = {
    "news": [
        {"name": "Times of India",  "url": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"},
        {"name": "NDTV",            "url": "https://feeds.feedburner.com/ndtvnews-top-stories"},
        {"name": "The Hindu",       "url": "https://www.thehindu.com/news/feeder/default.rss"},
        {"name": "BBC News India",  "url": "http://feeds.bbci.co.uk/news/world/asia/india/rss.xml"},
        {"name": "India Today",     "url": "https://www.indiatoday.in/rss/home"},
    ],
    "sports": [
        {"name": "ESPNcricinfo",    "url": "https://www.espncricinfo.com/rss/content/story/feeds/0.xml"},
        {"name": "BBC Sport",       "url": "http://feeds.bbci.co.uk/sport/rss.xml"},
        {"name": "Sportskeeda",     "url": "https://www.sportskeeda.com/feed"},
        {"name": "NDTV Sports",     "url": "https://feeds.feedburner.com/ndtvsports-latest"},
        {"name": "Cricbuzz",        "url": "https://www.cricbuzz.com/cricket-news/cricket-rss-feeds"},
    ],
    "tech": [
        {"name": "Hacker News",     "url": "https://news.ycombinator.com/rss"},
        {"name": "TechCrunch",      "url": "https://techcrunch.com/feed/"},
        {"name": "The Verge",       "url": "https://www.theverge.com/rss/index.xml"},
        {"name": "Dev.to",          "url": "https://dev.to/feed"},
    ],
    "science": [
        {"name": "NASA",            "url": "https://www.nasa.gov/rss/dyn/breaking_news.rss"},
        {"name": "Science Daily",   "url": "https://www.sciencedaily.com/rss/all.xml"},
        {"name": "New Scientist",   "url": "https://www.newscientist.com/feed/home/"},
    ],
    "finance": [
        {"name": "Moneycontrol",    "url": "https://www.moneycontrol.com/rss/latestnews.xml"},
        {"name": "Economic Times",  "url": "https://economictimes.indiatimes.com/rssfeedstopstories.cms"},
        {"name": "Yahoo Finance",   "url": "https://finance.yahoo.com/news/rssindex"},
    ],
}

CATEGORY_KEYWORDS = {
    "news": ["news", "today", "breaking", "latest", "headline", "update",
             "current", "event", "happen", "report", "2026"],
    "sports": ["cricket", "football", "ipl", "match", "score", "team",
               "player", "tournament", "sport", "fifa", "nba", "tennis",
               "yesterday", "won", "win", "lost", "league", "rcb", "csk",
               "mi", "kkr", "gt", "srh", "dc", "lsg", "pbks", "rr"],
    "tech": ["code", "coding", "programming", "software", "hardware", "ai",
             "tech", "developer", "python", "javascript", "startup", "app"],
    "science": ["science", "research", "study", "space", "nasa", "discovery",
                "experiment", "biology", "physics", "chemistry", "climate"],
    "finance": ["stock", "market", "crypto", "bitcoin", "investment", "price",
                "economy", "finance", "money", "trading", "nifty", "sensex"],
}

def detect_category(query):
    query_lower = query.lower()
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for word in keywords if word in query_lower)
        if score > 0:
            scores[category] = score
    if not scores:
        return "general"
    return max(scores, key=scores.get)

def tfidf_relevance(text, query, threshold=0.1):
    ## lightweight TF-IDF relevance check using sklearn
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        if not text or not query:
            return False

        vectorizer = TfidfVectorizer(stop_words="english")
        tfidf = vectorizer.fit_transform([text, query])
        score = cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]
        return score >= threshold
    except:
        ## fallback to keyword check if sklearn fails
        query_words = set(query.lower().split()) - {
            "what", "is", "the", "a", "an", "of", "in", "on",
            "for", "to", "and", "or", "how", "why", "who", "when", "where"
        }
        return sum(1 for w in query_words if w in text.lower()) >= 2

def scrape_article(url, max_words=400):
    try:
        headers = {"User-Agent": "LocalMind/1.0 (lokesh@student.unom.ac.in)"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200:
            return ""
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = soup.find_all("p")
        text = " ".join([p.get_text() for p in paragraphs])
        words = text.split()
        return " ".join(words[:max_words])
    except:
        return ""

def fetch_single_feed(feed, query, progress_callback=None):
    ## fetch one feed and check relevance per item
    relevant_items = []
    try:
        if progress_callback:
            progress_callback(f"[dim]  📡 checking {feed['name']}...[/dim]")

        parsed = feedparser.parse(feed["url"])

        for entry in parsed.entries[:5]:
            title = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))
            link = entry.get("link", "")
            published = entry.get("published", "")

            ## quick title relevance check first
            combined = f"{title} {summary}"
            if not tfidf_relevance(combined, query, threshold=0.05):
                continue

            ## scrape article for more content
            article_text = scrape_article(link) if link else ""

            if progress_callback:
                progress_callback(
                    f"[dim green]  ✓ relevant: {title[:50]}[/dim green]"
                )

            relevant_items.append({
                "source": feed["name"],
                "title": title,
                "summary": summary[:300] if summary else "",
                "article": article_text,
                "link": link,
                "published": published
            })

    except Exception as e:
        if progress_callback:
            progress_callback(f"[dim red]  ✗ {feed['name']} failed: {e}[/dim red]")

    return relevant_items

def get_context(query, progress_callback=None):
    category = detect_category(query)

    if category == "general":
        return None, category

    feeds = RSS_SOURCES.get(category, [])

    if progress_callback:
        progress_callback(
            f"[dim cyan]📡 {category.upper()} detected — checking {len(feeds)} RSS feeds...[/dim cyan]"
        )

    all_items = []

    ## check feeds one by one and collect relevant items
    for feed in feeds:
        items = fetch_single_feed(feed, query, progress_callback)
        all_items.extend(items)

    if not all_items:
        ## no relevant content found in any RSS feed
        if progress_callback:
            progress_callback(
                f"[dim yellow]⚠ No relevant content in RSS feeds — falling back to web search...[/dim yellow]"
            )
        return None, "general"  ## return general so pipeline falls back to DuckDuckGo

    ## format context
    context = f"Category: {category.upper()}\nQuery: {query}\n\n"
    for item in all_items:
        context += f"--- {item['source']} ---\n"
        context += f"Title: {item['title']}\n"
        if item['published']:
            context += f"Date: {item['published']}\n"
        if item['summary']:
            context += f"Summary: {item['summary']}\n"
        if item['article']:
            context += f"Article: {item['article']}\n"
        context += f"Link: {item['link']}\n\n"

    return context, category