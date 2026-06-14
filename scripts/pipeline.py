## File Name: pipeline.py
## Description: Main pipeline - AI decision maker + smart routing
## Path: scripts/pipeline.py
## Created By: Lokesh R     Created On: 2026-05-19
## Updated By: Lokesh R     Updated On: 2026-06-09
## Added date injection, AI decision maker, bad response detection

## Import - Libraries
import requests
import json
import time
from datetime import date

## Import - Application Program Files
from search import search_links
from scraper import scrape_text
from router import get_context

MAX_LINKS = 5
CHUNK_SIZE = 1500

## today's date injected into every prompt
TODAY = date.today().strftime("%B %d, %Y")

def get_model_options(model):
    model_lower = model.lower()
    if "tinyllama" in model_lower or ":1b" in model_lower:
        return {"num_predict": 256, "temperature": 0.1, "num_ctx": 1024}
    elif any(x in model_lower for x in ["3b", "phi", "gemma"]):
        return {"num_predict": 384, "temperature": 0.2, "num_ctx": 1536}
    else:
        return {"num_predict": 512, "temperature": 0.3, "num_ctx": 2048}

def is_bad_response(answer):
    bad_phrases = [
        "as an ai", "as a language model", "i cannot browse",
        "i don't have access", "my knowledge cutoff", "i am unable to",
        "without real-time", "i cannot directly", "as an artificial intelligence",
        "i don't have real-time", "i'm not able to access",
        "no matches have happened", "not yet taken place"
    ]
    answer_lower = answer.lower()
    return any(phrase in answer_lower for phrase in bad_phrases)

def rewrite_query(query, model):
    prompt = f"""<system>
You are a search engine optimization backend. Your job is to convert a raw user query into a clean, searchable keyword phrase.
CRITICAL RULES:
1. Output ONLY the raw optimized keywords.
2. Never include explanations, pleasantries, intro text, or system terms.
3. Keep the intent exactly identical.
</system>

User Query: "latest news on AI"
Optimized Keywords: latest artificial intelligence advancements news

User Query: "who won the ipl match in 2026 in india"
Optimized Keywords: 2026 Indian Premier League winner

User Query: "{query}"
Optimized Keywords:"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": -1,
                "options": {"num_predict": 30, "temperature": 0.1, "num_ctx": 512}
            }
        )
        rewritten = response.json().get("response", "").strip()
        rewritten = rewritten.replace('"', '').replace("'", '').split('\n')[0].strip()
        if not rewritten or len(rewritten) > 100:
            return query
        return rewritten
    except:
        return query

def decide_search_strategy(query, model):
    prompt = f"""You are a search router. Decide the best way to answer this query.

Options:
- rss: query is about recent news, sports scores, finance, tech news
- web: query needs specific facts, wikipedia info, detailed research
- both: query needs latest news AND detailed background info
- local: query is a simple question, math, general knowledge, conversation

Reply with ONLY one word: rss, web, both, or local

Query: {query}
Decision:"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": -1,
                "options": {"num_predict": 5, "temperature": 0.1, "num_ctx": 512}
            }
        )
        decision = response.json().get("response", "").strip().lower()
        decision = decision.split()[0] if decision else "web"
        if decision not in ["rss", "web", "both", "local"]:
            return "web"
        return decision
    except:
        return "web"

def build_prompt(query, context, source_title, chunk_index, total_chunks, model):
    model_lower = model.lower()
    date_ctx = f"Today's date is {TODAY}. Use this as reference for 'current', 'latest', 'now'.\n\n"
    system = f"You are LocalMind, a live-connected research engine. {date_ctx}Use the verified real-time context provided below. Ignore your training cutoff limits.\n\n"

    if "tinyllama" in model_lower or ":1b" in model_lower:
        return system + f"""Source: {source_title}
Text: {context}
Question: {query}
Answer briefly:"""

    elif any(x in model_lower for x in ["3b", "phi", "gemma"]):
        return system + f"""Text from {source_title} (part {chunk_index}/{total_chunks}):
{context}

Question: {query}
Give a clear answer:"""

    else:
        return system + f"""This is chunk {chunk_index} of {total_chunks} from "{source_title}".
Based ONLY on the text below, answer clearly and in detail. Do not extrapolate.

Text:
{context}

Question: {query}

Detailed answer:"""

def build_rss_prompt(query, context, model):
    model_lower = model.lower()
    date_ctx = f"Today's date is {TODAY}.\n\n"

    if "tinyllama" in model_lower or ":1b" in model_lower:
        return f"""{date_ctx}News data:
{context[:2000]}
Question: {query}
Answer briefly:"""

    elif any(x in model_lower for x in ["3b", "phi", "gemma"]):
        return f"""{date_ctx}You are a news assistant.
Based ONLY on this data below, answer the question directly.
Do not say you cannot access the internet — the data is already provided here.

Data:
{context[:3000]}

Question: {query}
Answer:"""

    else:
        return f"""{date_ctx}You are a research assistant.
Based ONLY on the data below, answer clearly and in detail.
Include dates, sources and headlines where available.

Data:
{context[:4000]}

Question: {query}

Answer:"""

def chunk_text(text):
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
                    if is_bad_response(answer):
                        final_text = label + "[bold yellow]⚠ Model couldn't answer from context — try different query[/bold yellow]"
                    else:
                        final_text = label + answer + f" [dim](generated in {gen_elapsed}s)[/dim]"
                    if chunk_callback and chunk_id:
                        chunk_callback("token", {"id": chunk_id, "text": final_text})
                    break

    except Exception as e:
        if chunk_callback:
            chunk_callback("token", {
                "id": chunk_id,
                "text": label + f"[bold red]Error: {e}[/bold red]"
            })

    return answer

def ask_localmind(query, max_links=MAX_LINKS, progress_callback=None, chunk_callback=None, stop_flag=None, model="mistral:latest"):

    ## step 0 — rewrite query
    if progress_callback:
        progress_callback("[dim]🧠 Understanding query...[/dim]")

    rewritten = rewrite_query(query, model)
    if rewritten != query and progress_callback:
        progress_callback(f"[dim cyan]🧠 Query understood as: {rewritten}[/dim cyan]")

    search_query = rewritten

    ## step 1 — AI decides strategy
    strategy = decide_search_strategy(query, model)
    if progress_callback:
        labels = {
            "rss":   "📡 Using trusted sources",
            "web":   "🌐 Searching the web",
            "both":  "📡🌐 Using RSS + web search",
            "local": "🤖 Answering from knowledge"
        }
        progress_callback(f"[dim cyan]{labels.get(strategy, '🌐 Searching')}...[/dim cyan]")

    ## step 2 — local strategy
    if strategy == "local":
        label = f"[bold cyan]LocalMind[/bold cyan] [dim](local knowledge):[/dim] "
        chunk_id = chunk_callback("start", label) if chunk_callback else None
        prompt = build_rss_prompt(query, "", model)
        stream_to_mistral(prompt, chunk_callback, chunk_id, label, stop_flag, model)
        return []

    rss_answer = ""

    ## step 3 — RSS/trusted sources
    if strategy in ["rss", "both"]:
        context, category = get_context(search_query, progress_callback=progress_callback)
        if context:
            if progress_callback:
                progress_callback(f"[dim cyan]📡 {category.upper()} — using RSS feeds...[/dim cyan]")
            label = f"[bold cyan]LocalMind[/bold cyan] [dim](via {category} RSS):[/dim] "
            chunk_id = chunk_callback("start", label) if chunk_callback else None
            prompt = build_rss_prompt(query, context, model)
            rss_answer = stream_to_mistral(prompt, chunk_callback, chunk_id, label, stop_flag, model)

            if strategy == "rss":
                return []

            ## if both and answer was good — stop here
            if not is_bad_response(rss_answer):
                return []

            if progress_callback:
                progress_callback("[dim yellow]📡 RSS not enough — also searching web...[/dim yellow]")

    ## step 4 — web search
    if progress_callback:
        progress_callback("[dim cyan]🌐 Searching the web...[/dim cyan]")

    links = search_links(search_query, max_results=max_links)

    if not links:
        if progress_callback:
            progress_callback("[bold red]No results found[/bold red]")
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
                progress_callback(f"[dim red]  ✗ could not scrape {link['title'][:40]}[/dim red]")
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
            chunk_id = chunk_callback("start", label) if chunk_callback else None

            prompt = build_prompt(query, chunk, link["title"], chunk_index+1, len(chunks), model)
            stream_to_mistral(prompt, chunk_callback, chunk_id, label, stop_flag, model)

    return sources