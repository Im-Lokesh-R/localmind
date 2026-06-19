## File Name: scraper.py
## Description: Fetches and cleans full article content from URLs
## Path: scripts/scraper.py
## Created By: Lokesh R     Created On: 2026-05-19
## Updated By: Lokesh R     Updated On: 2026-06-17
## Fixed: browser-like headers, retry with delay, better extraction

import requests
import time
from bs4 import BeautifulSoup

## browser-like headers — fixes most "non 200" blocks
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection":      "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

JUNK_TAGS = [
    "nav", "footer", "header", "script", "style",
    "aside", "form", "button", "iframe", "noscript",
    "advertisement", "figcaption", "svg", "img"
]

def _fetch(url, retries=2, delay=1.5):
    ## fetch with retry on failure
    for attempt in range(retries + 1):
        try:
            response = requests.get(
                url, headers=HEADERS, timeout=10
            )
            if response.status_code == 200:
                return response
            ## 403/429 — wait and retry
            if response.status_code in [403, 429, 503] and attempt < retries:
                time.sleep(delay)
                continue
            ## anything else — no point retrying
            return None
        except requests.exceptions.Timeout:
            if attempt < retries:
                time.sleep(delay)
            continue
        except Exception:
            return None
    return None

def _extract_text(soup):
    ## remove junk tags
    for tag in soup(JUNK_TAGS):
        tag.decompose()

    ## try specific content containers in priority order
    for selector in [
        "article",
        {"name": "main"},
        {"id": "content"},
        {"id": "main-content"},
        {"id": "article-body"},
        {"class_": "content"},
        {"class_": "article-body"},
        {"class_": "story-body"},
        {"class_": "post-content"},
        {"class_": "entry-content"},
        {"class_": "article-content"},
    ]:
        if isinstance(selector, str):
            el = soup.find(selector)
        else:
            el = soup.find(**selector)
        if el:
            text = el.get_text(separator=" ")
            if len(text.split()) > 50:  ## ignore tiny matches
                return text

    ## fallback — join all paragraphs
    paragraphs = soup.find_all("p")
    if paragraphs:
        return " ".join(p.get_text() for p in paragraphs)

    ## last resort — full body text
    body = soup.find("body")
    if body:
        return body.get_text(separator=" ")

    return ""

def scrape_text(url, max_words=3000):
    response = _fetch(url)
    if not response:
        return ""

    try:
        soup = BeautifulSoup(response.text, "html.parser")
        text = _extract_text(soup)
        text = " ".join(text.split())
        words = text.split()
        return " ".join(words[:max_words])
    except:
        return ""

def scrape_sections(url, max_words_per_section=500):
    response = _fetch(url)
    if not response:
        return []

    try:
        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(JUNK_TAGS):
            tag.decompose()

        sections = []
        headings = soup.find_all(["h1", "h2", "h3"])

        if headings:
            for heading in headings:
                title = heading.get_text().strip()
                if not title or len(title) < 3 or len(title) > 120:
                    continue

                content = []
                for sibling in heading.find_next_siblings():
                    if sibling.name in ["h1", "h2", "h3"]:
                        break
                    if sibling.name in ["p", "li", "td", "dd"]:
                        text = sibling.get_text().strip()
                        if text:
                            content.append(text)

                content_text = " ".join(content)
                words = content_text.split()
                if len(words) > 20:
                    sections.append({
                        "index":      len(sections) + 1,
                        "title":      title[:60],
                        "content":    " ".join(words[:max_words_per_section]),
                        "word_count": len(words)
                    })

        ## fallback — chunk by paragraphs if no headings found
        if not sections:
            paragraphs = soup.find_all("p")
            chunk, chunk_len, section_num = [], 0, 1

            for p in paragraphs:
                text = p.get_text().strip()
                if not text:
                    continue
                chunk.append(text)
                chunk_len += len(text.split())

                if chunk_len >= 200:
                    sections.append({
                        "index":      section_num,
                        "title":      f"Section {section_num}",
                        "content":    " ".join(chunk),
                        "word_count": chunk_len
                    })
                    section_num += 1
                    chunk, chunk_len = [], 0

            if chunk:
                sections.append({
                    "index":      section_num,
                    "title":      f"Section {section_num}",
                    "content":    " ".join(chunk),
                    "word_count": chunk_len
                })

        return sections

    except:
        return []


## test
if __name__ == "__main__":
    sections = scrape_sections("https://en.wikipedia.org/wiki/FIFA_World_Cup")
    for s in sections[:5]:
        print(f"[{s['index']}] {s['title']} ({s['word_count']} words)")