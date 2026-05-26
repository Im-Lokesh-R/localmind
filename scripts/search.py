## File Name: search.py
## Description: Uses DuckDuckGo to find top relevant links for a query
## Path: scripts/search.py
## Created By: Lokesh R     Created On: 2026-05-19

## Import - Libraries
from ddgs import DDGS


def search_links(query, max_results=5):
    ## search DuckDuckGo and get top results
    results = []

    with DDGS() as ddgs:
        for result in ddgs.text(query, max_results=max_results):
            results.append({
                "title": result["title"],
                "url": result["href"],
                "snippet": result["body"]
            })

    return results


## Test it
if __name__ == "__main__":
    links = search_links("What is a black hole")
    for link in links:
        print(link["title"])
        print(link["url"])
        print()