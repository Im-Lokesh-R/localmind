## File Name: search.py
## Description: Multi-source search - DuckDuckGo, Wikipedia, arXiv
## Path: scripts/search.py
## Created By: Lokesh R     Created On: 2026-05-19
## Updated By: Lokesh R     Updated On: 2026-06-15
## Added Wikipedia API and arXiv API as free search sources

## Import - Libraries
import requests
from ddgs import DDGS

def search_links(query, max_results=5):
    ## DuckDuckGo search
    results = []
    try:
        with DDGS() as ddgs:
            for result in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": result["title"],
                    "url": result["href"],
                    "snippet": result["body"],
                    "source": "duckduckgo"
                })
    except:
        pass
    return results

def search_wikipedia(query, max_results=3):
    ## Wikipedia API search — returns clean summaries directly
    results = []
    try:
        ## search for pages
        search_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": max_results,
            "format": "json"
        }
        headers = {"User-Agent": "LocalMind/1.0 (lokesh@student.unom.ac.in)"}
        response = requests.get(search_url, params=params, headers=headers, timeout=5)
        data = response.json()

        for item in data.get("query", {}).get("search", []):
            page_title = item["title"]

            ## get full extract for this page
            extract_params = {
                "action": "query",
                "titles": page_title,
                "prop": "extracts",
                "exintro": False,
                "explaintext": True,
                "format": "json"
            }
            extract_response = requests.get(search_url, params=extract_params,
                                            headers=headers, timeout=5)
            extract_data = extract_response.json()
            pages = extract_data.get("query", {}).get("pages", {})

            for page_id, page in pages.items():
                extract = page.get("extract", "")
                if extract:
                    results.append({
                        "title": page_title,
                        "url": f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}",
                        "content": extract[:3000],
                        "source": "wikipedia"
                    })

    except:
        pass
    return results

def search_arxiv(query, max_results=3):
    ## arXiv API — free research papers, no key needed
    results = []
    try:
        url = "http://export.arxiv.org/api/query"
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending"
        }
        headers = {"User-Agent": "LocalMind/1.0 (lokesh@student.unom.ac.in)"}
        response = requests.get(url, params=params, headers=headers, timeout=8)

        ## parse XML response
        from xml.etree import ElementTree as ET
        root = ET.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns)
            summary = entry.find("atom:summary", ns)
            link = entry.find("atom:id", ns)

            if title is not None and summary is not None:
                results.append({
                    "title": title.text.strip(),
                    "url": link.text.strip() if link is not None else "",
                    "content": summary.text.strip()[:2000],
                    "source": "arxiv"
                })

    except:
        pass
    return results

def multi_search(query, max_results=5, use_wikipedia=True, use_arxiv=False):
    ## combine multiple search sources
    all_results = []

    ## always use DuckDuckGo
    ddg_results = search_links(query, max_results=max_results)
    all_results.extend(ddg_results)

    ## add Wikipedia for research queries
    if use_wikipedia:
        wiki_results = search_wikipedia(query, max_results=2)
        all_results.extend(wiki_results)

    ## add arXiv for research/science queries
    if use_arxiv:
        arxiv_results = search_arxiv(query, max_results=2)
        all_results.extend(arxiv_results)

    return all_results

## Test
if __name__ == "__main__":
    results = multi_search("FIFA World Cup 2026")
    for r in results:
        print(f"[{r['source']}] {r['title']}")
        print(f"  {r['url']}")
        print()