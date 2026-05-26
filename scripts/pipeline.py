## File Name: pipeline.py
## Description: Main pipeline - search, scrape and generate answer using Mistral
## Path: scripts/pipeline.py
## Created By: Lokesh R     Created On: 2026-05-19

## Import - Libraries
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

## Import - Application Program Files
from search import search_links
from scraper import scrape_text

## max links to scrape (can be changed via /links command)
MAX_LINKS = 5

def ask_localmind(query, max_links=MAX_LINKS, progress_callback=None):

    ## step 1: find top links using DuckDuckGo
    links = search_links(query, max_results=max_links)

    ## step 2: scrape all links in parallel using threads
    all_text = ""
    sources = []

    def fetch(link):
        if progress_callback:
            progress_callback(f"  → visiting {link['url'][:60]}...")
        text = scrape_text(link["url"])
        if progress_callback and text:
            progress_callback(f"  ✓ scraped {link['title'][:40]}")
        return link, text

    with ThreadPoolExecutor(max_workers=max_links) as executor:
        futures = {executor.submit(fetch, link): link for link in links}
        for future in as_completed(futures):
            link, text = future.result()
            if text:
                all_text += f"\n\n--- Source: {link['title']} ---\n{text}"
                sources.append(link["title"])
                sources.append(link["url"])

    ## step 3: estimate response time based on context size
    word_count = len(all_text.split())
    estimated_seconds = round((word_count / 500) * 12)

    if progress_callback:
        progress_callback(f"📊 Context: {word_count} words scraped from {len(sources) // 2} sources")
        progress_callback(f"⏳ Estimated response time: ~{estimated_seconds}s")
        progress_callback(f"🤖 Generating detailed answer...")

    ## step 4: build the prompt

    prompt = f"""You are a detailed research assistant.
Your job is to organize and present ALL the information from the sources below in a clear, structured, and comprehensive way.
Do NOT summarize or shorten the content.
Present everything in full detail with proper headings and structure.
Only use the context provided — do not add your own knowledge.

Context:
{all_text[:8000]}

Question:
{query}

Give a detailed, well organized, comprehensive answer:"""

    ## step 5: send to Mistral
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "mistral",
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 2048,
                "temperature": 0.3
            }
        }
    )

    result = response.json()

    if "error" in result:
        return f"Error: {result['error']}", [], estimated_seconds

    return result["response"], sources, estimated_seconds