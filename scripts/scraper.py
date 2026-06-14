## File Name: scraper.py
## Description: Fetches and cleans article content from URLs
## Path: scripts/scraper.py
## Created By: Lokesh R     Created On: 2026-05-19
## Updated By: Lokesh R     Updated On: 2026-06-09
## Better article extraction, removes nav/footer junk

## Import - Libraries
import requests
from bs4 import BeautifulSoup

def scrape_text(url, max_words=800):
    try:
        headers = {"User-Agent": "LocalMind/1.0 (lokesh@student.unom.ac.in)"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(response.text, "html.parser")

        ## remove junk elements
        for tag in soup(["nav", "footer", "header", "script",
                         "style", "aside", "form", "button",
                         "iframe", "noscript", "advertisement"]):
            tag.decompose()

        ## try article tag first — most news sites use it
        article = soup.find("article")
        if article:
            text = article.get_text(separator=" ")
        else:
            ## try main content area
            main = (soup.find("main") or
                    soup.find(id="content") or
                    soup.find(id="main-content") or
                    soup.find(class_="content") or
                    soup.find(class_="article-body") or
                    soup.find(class_="story-body"))
            if main:
                text = main.get_text(separator=" ")
            else:
                ## last resort — all paragraphs
                paragraphs = soup.find_all("p")
                text = " ".join([p.get_text() for p in paragraphs])

        ## clean whitespace
        text = " ".join(text.split())
        words = text.split()
        return " ".join(words[:max_words])

    except:
        return ""

## Test it
if __name__ == "__main__":
    text = scrape_text("https://en.wikipedia.org/wiki/Black_hole")
    print(text[:500])