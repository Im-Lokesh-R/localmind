## File Name: pipeline.py
## Description: Main pipeline - RSS routing + sequential scrape and chunk streaming
## Path: scripts/pipeline.py
## Created By: Lokesh R     Created On: 2026-05-19
## Updated By: Lokesh R     Updated On: 2026-05-27
## Added RSS router, relevance check, chunk streaming

## Import - Libraries
import requests
import json

## Import - Application Program Files
from search import search_links
from scraper import scrape_text
from router import get_context

MAX_LINKS = 5
CHUNK_SIZE = 1500

def chunk_text(text):
    ## split text into chunks of CHUNK_SIZE characters word by word
    words = text.split()
    chunks = []
    current = []
    current_len = 0

    for word in words:
        current_len += len(word) + 1
        current.append(word)
        if current_len >= CHUNK_SIZE:
            chunks.append(" ".join(current))
            current = []
            current_len = 0

    if current:
        chunks.append(" ".join(current))

    return chunks

def is_relevant(chunk, query):
    ## quick keyword check before sending chunk to Mistral
    query_words = set(query.lower().split())

    ## remove common words that appear everywhere
    stop_words = {"what", "is", "the", "a", "an", "of", "in", "on", "for",
                  "to", "and", "or", "how", "why", "who", "when", "where",
                  "list", "tell", "me", "about", "today", "latest", "news"}

    query_words = query_words - stop_words
    chunk_lower = chunk.lower()

    ## need at least 2 query keywords in the chunk
    matches = sum(1 for word in query_words if word in chunk_lower)
    return matches >= 2

def stream_to_mistral(prompt, chunk_callback, chunk_id, label, stop_flag, model="mistral:latest"):
    ## shared function to stream any prompt to Mistral
    answer = ""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": True,
                "keep_alive": -1,
                "options": {
                    "num_predict": 512,
                    "temperature": 0.3,
                    "num_ctx": 2048
                }
            },
            stream=True
        )

        for line in response.iter_lines():
            if stop_flag and stop_flag():
                break
            if line:
                data = json.loads(line.decode("utf-8"))
                token = data.get("response", "")
                answer += token

                if chunk_callback and chunk_id:
                    chunk_callback("token", {
                        "id": chunk_id,
                        "text": label + answer
                    })

                if data.get("done"):
                    break

    except Exception as e:
        if chunk_callback:
            chunk_callback("token", {
                "id": chunk_id,
                "text": label + f"[bold red]Error: {e}[/bold red]"
            })

    return answer

def ask_localmind(query, max_links=MAX_LINKS, progress_callback=None, chunk_callback=None, stop_flag=None, model="mistral:latest"):
    context, category = get_context(query, progress_callback=progress_callback)

    if context:
        ## RSS route — fast, reliable, no scraping needed
        if progress_callback:
            progress_callback(
                f"[dim cyan]📡 {category.upper()} query detected — using RSS feeds...[/dim cyan]"
            )

        label = f"[bold cyan]LocalMind[/bold cyan] [dim](via {category} RSS):[/dim] "
        chunk_id = None

        if chunk_callback:
            chunk_id = chunk_callback("start", label)

        prompt = f"""You are a research assistant.
Based ONLY on the RSS feed data below, answer the question clearly and in detail.
Include dates, sources and headlines where available.
Do not add anything from your own knowledge.

RSS Data:
{context[:4000]}

Question: {query}

Answer:"""

        stream_to_mistral(prompt, chunk_callback, chunk_id, label, stop_flag, model)
        ## return empty sources since RSS has inline source labels
        return []

    ## ── step 1: general query — use DuckDuckGo pipeline ────────────────
    if progress_callback:
        progress_callback("[dim cyan]🌐 General query — searching the web...[/dim cyan]")

    links = search_links(query, max_results=max_links)

    if not links:
        if progress_callback:
            progress_callback("[bold red]No results found from DuckDuckGo[/bold red]")
        return []

    if progress_callback:
        progress_callback(f"[dim]✓ Found {len(links)} links — scraping now...[/dim]")

    sources = []

    ## ── step 2: one site at a time ──────────────────────────────────────
    for site_index, link in enumerate(links):

        if stop_flag and stop_flag():
            break

        if progress_callback:
            progress_callback(
                f"[dim]→ [{site_index+1}/{len(links)}] visiting {link['url'][:60]}...[/dim]"
            )

        text = scrape_text(link["url"])

        if not text:
            if progress_callback:
                progress_callback(
                    f"[dim red]  ✗ could not scrape {link['title'][:40]}[/dim red]"
                )
            continue

        sources.append(link["title"])
        sources.append(link["url"])

        chunks = chunk_text(text)

        if progress_callback:
            progress_callback(
                f"[dim green]  ✓ scraped {link['title'][:40]} → {len(chunks)} chunks[/dim green]"
            )

        ## ── step 3: feed each relevant chunk ────────────────────────────
        for chunk_index, chunk in enumerate(chunks):

            if stop_flag and stop_flag():
                break

            ## relevance check — skip irrelevant chunks
            if not is_relevant(chunk, query):
                if progress_callback:
                    progress_callback(
                        f"[dim]  ⏭ skipping chunk {chunk_index+1}/{len(chunks)} — not relevant[/dim]"
                    )
                continue

            if progress_callback:
                progress_callback(
                    f"[dim]  📤 feeding chunk {chunk_index+1}/{len(chunks)} from {link['title'][:30]}...[/dim]"
                )

            label = f"[bold cyan]LocalMind[/bold cyan] [dim]({link['title'][:25]} · chunk {chunk_index+1}/{len(chunks)}):[/dim] "

            chunk_id = None
            if chunk_callback:
                chunk_id = chunk_callback("start", label)

            prompt = f"""You are a research assistant analyzing a piece of text.
This is chunk {chunk_index+1} of {len(chunks)} from the source "{link['title']}".
Based ONLY on the text below, answer the question clearly and in detail.
Do not add anything from your own knowledge.
If this chunk does not contain relevant information, say "No relevant info in this chunk."

Text:
{chunk}

Question: {query}

Answer:"""

            stream_to_mistral(prompt, chunk_callback, chunk_id, label, stop_flag)

    return sources