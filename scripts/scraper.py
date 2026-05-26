## File Name: scraper.py
## Description: Fetches and cleans text content from a given URL
## Path: scripts/scraper.py
## Created By: Lokesh R     Created On: 2026-05-19

## Import - Libraries
import requests
from bs4 import BeautifulSoup


def scrape_text(url):
    try:
        ## fetch the page
        headers = {
            "User-Agent": "LocalMind/1.0 (your@email.com)"
        }
        response = requests.get(url, headers=headers, timeout=5)

        ## check if request was successful
        if response.status_code != 200:
            return ""

        ## parse the HTML
        soup = BeautifulSoup(response.text, "html.parser")

        ## extract only paragraph text
        paragraphs = soup.find_all("p")

        ## join all paragraphs into one clean text
        clean_text = " ".join([p.get_text() for p in paragraphs])

        ## return first 2000 words only
        words = clean_text.split()
        return " ".join(words[:2000])

    except Exception as e:
        ## if any site fails just skip it
        return ""


## Test it
if __name__ == "__main__":
    text = scrape_text("https://en.wikipedia.org/wiki/Black_hole")
    print(text[:500])