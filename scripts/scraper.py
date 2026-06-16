## File Name: scraper.py
## Description: Fetches and cleans full article content from URLs
## Path: scripts/scraper.py
## Created By: Lokesh R     Created On: 2026-05-19
## Updated By: Lokesh R     Updated On: 2026-06-15
## Full article extraction, section splitting, 3000 word limit

## Import - Libraries
import requests
from bs4 import BeautifulSoup

def scrape_text(url, max_words=3000):
    try:
        headers = {"User-Agent": "LocalMind/1.0 (lokesh@student.unom.ac.in)"}
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(response.text, "html.parser")

        ## remove junk
        for tag in soup(["nav", "footer", "header", "script",
                         "style", "aside", "form", "button",
                         "iframe", "noscript", "advertisement"]):
            tag.decompose()

        ## try article tag first
        article = soup.find("article")
        if article:
            text = article.get_text(separator=" ")
        else:
            main = (soup.find("main") or
                    soup.find(id="content") or
                    soup.find(id="main-content") or
                    soup.find(class_="content") or
                    soup.find(class_="article-body") or
                    soup.find(class_="story-body"))
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

def scrape_sections(url, max_words_per_section=500):
    ## scrape page and split into named sections for user to pick
    try:
        headers = {"User-Agent": "LocalMind/1.0 (lokesh@student.unom.ac.in)"}
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["nav", "footer", "header", "script",
                         "style", "aside", "form", "button", "iframe"]):
            tag.decompose()

        sections = []

        ## try to find headings and their content
        headings = soup.find_all(["h1", "h2", "h3"])

        if headings:
            for i, heading in enumerate(headings):
                title = heading.get_text().strip()
                if not title or len(title) < 3:
                    continue

                ## get text between this heading and the next
                content = []
                for sibling in heading.find_next_siblings():
                    if sibling.name in ["h1", "h2", "h3"]:
                        break
                    if sibling.name == "p":
                        content.append(sibling.get_text())

                content_text = " ".join(content)
                words = content_text.split()
                if len(words) > 20:  ## skip empty sections
                    sections.append({
                        "index": len(sections) + 1,
                        "title": title[:60],
                        "content": " ".join(words[:max_words_per_section]),
                        "word_count": len(words)
                    })

        ## fallback — split by paragraphs if no headings
        if not sections:
            paragraphs = soup.find_all("p")
            chunk = []
            chunk_len = 0
            section_num = 1

            for p in paragraphs:
                text = p.get_text().strip()
                if not text:
                    continue
                chunk.append(text)
                chunk_len += len(text.split())

                if chunk_len >= 200:
                    sections.append({
                        "index": section_num,
                        "title": f"Section {section_num}",
                        "content": " ".join(chunk),
                        "word_count": chunk_len
                    })
                    section_num += 1
                    chunk = []
                    chunk_len = 0

            if chunk:
                sections.append({
                    "index": section_num,
                    "title": f"Section {section_num}",
                    "content": " ".join(chunk),
                    "word_count": chunk_len
                })

        return sections

    except:
        return []

## Test
if __name__ == "__main__":
    sections = scrape_sections("https://en.wikipedia.org/wiki/FIFA_World_Cup")
    for s in sections[:5]:
        print(f"[{s['index']}] {s['title']} ({s['word_count']} words)")