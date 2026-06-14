## File Name: router.py
## Description: Smart source routing using trusted domains + DuckDuckGo
## Path: scripts/router.py
## Created By: Lokesh R     Created On: 2026-05-27
## Updated By: Lokesh R     Updated On: 2026-06-09
## Dynamic site-targeted search, parallel fetching, result-specific targeting

## Import - Libraries
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from concurrent.futures import ThreadPoolExecutor, as_completed

TRUSTED_SOURCES = {
    "news": [
        "bbc.com", "reuters.com", "ndtv.com",
        "thehindu.com", "timesofindia.com", "aljazeera.com"
    ],
    "sports": [
        "espn.com", "bbc.com/sport", "cricbuzz.com",
        "espncricinfo.com", "goal.com", "sportskeeda.com"
    ],
    "tech": [
        "techcrunch.com", "theverge.com",
        "wired.com", "arstechnica.com", "dev.to"
    ],
    "science": [
        "nasa.gov", "sciencedaily.com",
        "newscientist.com", "nature.com"
    ],
    "finance": [
        "moneycontrol.com", "economictimes.indiatimes.com",
        "bloomberg.com", "finance.yahoo.com"
    ],
}

CATEGORY_KEYWORDS = {
    "news": ["news", "today", "breaking", "latest", "headline", "update",
             "current", "event", "happen", "report", "2026"],
    "sports": ["cricket", "football", "ipl", "match", "score", "team",
               "player", "tournament", "sport", "fifa", "world cup", "nba",
               "tennis", "yesterday", "won", "win", "lost", "league",
               "rcb", "csk", "mi", "kkr", "gt", "srh", "dc", "lsg", "pbks", "rr"],
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

def enhance_query(query):
    ## add result-specific terms to improve targeting
    query_lower = query.lower()
    if any(w in query_lower for w in ["result", "match", "score", "won", "winner", "happened"]):
        return f"{query} results scores"
    if any(w in query_lower for w in ["latest", "today", "now", "current", "so far"]):
        return f"{query} 2026 latest"
    return query

def search_trusted_source(query, domain, max_results=2):
    ## search DuckDuckGo targeting a specific trusted domain
    results = []
    try:
        enhanced = enhance_query(query)
        with DDGS() as ddgs:
            for r in ddgs.text(f"{enhanced} site:{domain}", max_results=max_results):
                results.append({
                    "title": r["title"],
                    "url": r["href"],
                    "snippet": r["body"]
                })
    except:
        pass
    return results

def scrape_article(url, max_words=500):
    try:
        headers = {"User-Agent": "LocalMind/1.0 (lokesh@student.unom.ac.in)"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200:
            return ""
        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["nav", "footer", "header", "script",
                         "style", "aside", "form", "button", "iframe"]):
            tag.decompose()

        article = soup.find("article")
        if article:
            text = article.get_text(separator=" ")
        else:
            main = (soup.find("main") or
                    soup.find(id="content") or
                    soup.find(class_="content") or
                    soup.find(class_="article-body"))
            if main:
                text = main.get_text(separator=" ")
            else:
                paragraphs = soup.find_all("p")
                text = " ".join([p.get_text() for p in paragraphs])

        text = " ".join(text.split())
        words = text.split()
        return " ".join(words[:max_words])
    except:
        return ""

def get_context(query, progress_callback=None):
    category = detect_category(query)

    if category == "general":
        return None, category

    domains = TRUSTED_SOURCES.get(category, [])

    if progress_callback:
        progress_callback(
            f"[dim cyan]📡 {category.upper()} detected — searching {len(domains)} trusted sources...[/dim cyan]"
        )

    all_items = []

    def fetch_domain(domain):
        results = search_trusted_source(query, domain, max_results=2)
        items = []
        for r in results:
            article_text = scrape_article(r["url"])
            items.append({
                "source": domain,
                "title": r["title"],
                "snippet": r["snippet"],
                "article": article_text,
                "url": r["url"]
            })
        return domain, items

    ## search all domains in parallel
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fetch_domain, d): d for d in domains[:3]}
        for future in as_completed(futures):
            domain, items = future.result()
            if items and progress_callback:
                for item in items:
                    progress_callback(
                        f"[dim green]  ✓ found: {item['title'][:50]}[/dim green]"
                    )
            all_items.extend(items)

    if not all_items:
        if progress_callback:
            progress_callback(
                "[dim yellow]⚠ No content from trusted sources — falling back to web search...[/dim yellow]"
            )
        return None, "general"

    ## format context
    context = f"Category: {category.upper()}\nQuery: {query}\n\n"
    for item in all_items:
        context += f"--- {item['source']} ---\n"
        context += f"Title: {item['title']}\n"
        if item['snippet']:
            context += f"Snippet: {item['snippet']}\n"
        if item['article']:
            context += f"Article: {item['article']}\n"
        context += f"URL: {item['url']}\n\n"

    return context, category