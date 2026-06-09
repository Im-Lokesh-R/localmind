## File Name: pipeline.py
## Description: Main pipeline - RSS routing + sequential scrape and chunk streaming
## Path: scripts/pipeline.py
## Created By: Lokesh R     Created On: 2026-05-19
## Updated By: Lokesh R     Updated On: 2026-06-02
## Added model-aware prompt building and dynamic options

## Import - Libraries
import requests
import json
import time
## Import - Application Program Files
from search import search_links
from scraper import scrape_text
from router import get_context

MAX_LINKS = 5
CHUNK_SIZE = 1500

def get_model_options(model):
    ## adjust options based on model size
    model_lower = model.lower()
    if "tinyllama" in model_lower or ":1b" in model_lower:
        return {"num_predict": 256, "temperature": 0.1, "num_ctx": 1024}
    elif any(x in model_lower for x in ["3b", "phi", "gemma"]):
        return {"num_predict": 384, "temperature": 0.2, "num_ctx": 1536}
    else:
        return {"num_predict": 512, "temperature": 0.3, "num_ctx": 2048}

def build_prompt(query, context, source_title, chunk_index, total_chunks, model):
    ## build prompt based on model capability
    model_lower = model.lower()

    if "tinyllama" in model_lower or ":1b" in model_lower:
        ## tiny model — ultra simple, direct
        return f"""Source: {source_title}
Text: {context}
Question: {query}
Answer briefly:"""

    elif any(x in model_lower for x in ["3b", "phi", "gemma"]):
        ## small model — simple but structured
        return f"""You are a research assistant.
Text from {source_title} (part {chunk_index}/{total_chunks}):
{context}

Question: {query}
Give a clear answer:"""

    else:
        ## 7B+ model — full detailed prompt
        return f"""You are a detailed research assistant.
This is chunk {chunk_index} of {total_chunks} from "{source_title}".
Based ONLY on the text below, answer clearly and in detail.
Do not add anything from your own knowledge.
If this chunk has no relevant info, say "No relevant info in this chunk."

Text:
{context}

Question: {query}

Detailed answer:"""

def build_rss_prompt(query, context, model):
    ## build RSS prompt based on model capability
    model_lower = model.lower()

    if "tinyllama" in model_lower or ":1b" in model_lower:
        return f"""News data:
{context[:2000]}
Question: {query}
Answer briefly:"""

    elif any(x in model_lower for x in ["3b", "phi", "gemma"]):
        return f"""You are a news assistant.
Based on this RSS data, answer the question:
{context[:3000]}

Question: {query}
Answer:"""

    else:
        return f"""You are a research assistant.
Based ONLY on the RSS feed data below, answer clearly and in detail.
Include dates, sources and headlines where available.
Do not add anything from your own knowledge.

RSS Data:
{context[:4000]}

Question: {query}

Answer:"""

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
    ## quick keyword check before sending chunk to model
    query_words = set(query.lower().split())

    stop_words = {"what", "is", "the", "a", "an", "of", "in", "on", "for",
                  "to", "and", "or", "how", "why", "who", "when", "where",
                  "list", "tell", "me", "about", "today", "latest", "news"}

    query_words = query_words - stop_words
    chunk_lower = chunk.lower()
    matches = sum(1 for word in query_words if word in chunk_lower)
    return matches >= 2

def stream_to_mistral(prompt, chunk_callback, chunk_id, label, stop_flag, model="mistral:latest"):
    answer = ""
    options = get_model_options(model)
    gen_start = time.time()

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": True,
                "keep_alive": -1,
                "options": options
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
                    gen_elapsed = round(time.time() - gen_start, 1)
                    ## show generation time inline
                    if chunk_callback and chunk_id:
                        chunk_callback("token", {
                            "id": chunk_id,
                            "text": label + answer + f" [dim](generated in {gen_elapsed}s)[/dim]"
                        })
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
        if progress_callback:
            progress_callback(
                f"[dim cyan]📡 {category.upper()} query detected — using RSS feeds...[/dim cyan]"
            )

        label = f"[bold cyan]LocalMind[/bold cyan] [dim](via {category} RSS):[/dim] "
        chunk_id = None

        if chunk_callback:
            chunk_id = chunk_callback("start", label)

        ## use model-aware RSS prompt
        prompt = build_rss_prompt(query, context, model)

        stream_to_mistral(prompt, chunk_callback, chunk_id, label, stop_flag, model)
        return []

    ## ── general query — DuckDuckGo pipeline ─────────────────────────────
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

        for chunk_index, chunk in enumerate(chunks):

            if stop_flag and stop_flag():
                break

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

            ## use model-aware chunk prompt
            prompt = build_prompt(
                query, chunk,
                link["title"], chunk_index+1, len(chunks),
                model
            )

            stream_to_mistral(prompt, chunk_callback, chunk_id, label, stop_flag, model)

    return sources