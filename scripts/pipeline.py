## File Name: pipeline.py
## Description: Human-in-the-loop pipeline — query, links, then per-link generation choice
## Path: scripts/pipeline.py
## Created By: Lokesh R     Created On: 2026-05-19
## Updated By: Lokesh R     Updated On: 2026-06-17
## Simplified: 1 chunk per link, scrape all selected first, pick which to generate from

import requests
import json
import time
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from search import search_links, search_wikipedia, search_arxiv
from scraper import scrape_text
import panel_bridge as bridge

MAX_LINKS  = 5
TODAY           = date.today().strftime("%B %d, %Y")
TODAY_SHORT     = date.today().strftime("%Y-%m-%d")
YESTERDAY       = (date.today() - timedelta(days=1)).strftime("%B %d, %Y")
YESTERDAY_SHORT = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
CURRENT_YEAR    = date.today().strftime("%Y")
CURRENT_MONTH   = date.today().strftime("%B %Y")

## ── model helpers ─────────────────────────────────────────────────────────────

def get_model_options(model):
    m = model.lower()
    if "tinyllama" in m or ":1b" in m:
        return {"num_predict": 256, "temperature": 0.1, "num_ctx": 1024}
    elif any(x in m for x in ["3b", "phi", "gemma"]):
        return {"num_predict": 512, "temperature": 0.2, "num_ctx": 2048}
    else:
        return {"num_predict": 768, "temperature": 0.3, "num_ctx": 4096}

def is_bad_response(answer):
    bad = [
        "as an ai", "as a language model", "i cannot browse",
        "i don't have access", "my knowledge cutoff", "i am unable to",
        "without real-time", "i cannot directly", "as an artificial intelligence",
        "i don't have real-time", "i'm not able to access",
        "no matches have happened", "not yet taken place",
        "as of my last update", "my last update", "i cannot access real-time",
        "i don't have the ability to access", "my training data",
        "i was trained", "based on my training", "i lack access",
        "i do not have access to live", "i cannot provide real-time",
        "please note that i", "as of my knowledge"
    ]
    return any(p in answer.lower() for p in bad)

## ── date helpers ──────────────────────────────────────────────────────────────

def resolve_time_references(query):
    q = query.lower()
    replacements = {
        "yesterday":  YESTERDAY_SHORT,
        "today":      TODAY_SHORT,
        "this week":  f"week of {TODAY_SHORT}",
        "this month": CURRENT_MONTH,
        "this year":  CURRENT_YEAR,
        "latest":     f"latest {CURRENT_YEAR}",
        "recent":     f"recent {CURRENT_YEAR}",
        "now":        TODAY_SHORT,
        "currently":  TODAY_SHORT,
        "last night": YESTERDAY_SHORT,
        "tonight":    TODAY_SHORT,
    }
    for word, replacement in replacements.items():
        if word in q:
            return query.lower().replace(word, replacement)
    return query

## ── step 1: generate 3 query rewrites ────────────────────────────────────────

def generate_query_variants(query, model):
    time_resolved = resolve_time_references(query)

    prompt = f"""You are a search engine expert. Today is {TODAY}.
Generate exactly 3 different search-optimized versions of the user query below.
Each version should approach the search from a slightly different angle.
Always include the year {CURRENT_YEAR} for news/sports/events queries.
If query has time words like yesterday/today, use the actual date: {YESTERDAY_SHORT} or {TODAY_SHORT}.

Output ONLY this exact format — 3 lines, no numbering, no explanation:
<query1>
<query2>
<query3>

User query: {time_resolved}
Output:"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": -1,
                "options": {"num_predict": 80, "temperature": 0.4, "num_ctx": 512}
            },
            timeout=30
        )
        raw      = response.json().get("response", "").strip()
        lines    = [l.strip() for l in raw.split("\n") if l.strip()]
        variants = lines[:3]
        while len(variants) < 3:
            variants.append(time_resolved)
        return variants[:3]
    except:
        return [time_resolved, time_resolved, time_resolved]

## ── prompt builder ─────────────────────────────────────────────────────────────

def build_prompt(query, context, source_title, model):
    m        = model.lower()
    date_ctx = (
        f"Today is {TODAY}. Yesterday was {YESTERDAY}. Year: {CURRENT_YEAR}.\n"
    )
    system = (
        f"IMPORTANT: You have LIVE scraped data from the internet. {date_ctx}"
        f"Answer using ONLY the text below. "
        f"Do NOT mention training cutoff or inability to access internet. "
        f"If the answer is in the text, state it directly and confidently.\n\n"
    )
    if "tinyllama" in m or ":1b" in m:
        return (
            system +
            f"Source: {source_title}\nText: {context}\n"
            f"Question: {query}\nAnswer:"
        )
    elif any(x in m for x in ["3b", "phi", "gemma"]):
        return (
            system +
            f"=== LIVE DATA FROM {source_title.upper()} ===\n"
            f"{context}\n=== END ===\n\n"
            f"Question: {query}\n"
            f"Answer (specific, from data above):"
        )
    else:
        return (
            system +
            f"Source: \"{source_title}\":\n"
            f"{context}\n\nQuestion: {query}\nDetailed answer:"
        )

## ── streaming ─────────────────────────────────────────────────────────────────

def stream_to_model(prompt, chunk_callback, chunk_id, label, stop_flag, model):
    answer    = ""
    options   = get_model_options(model)
    gen_start = time.time()

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model":    model,
                "prompt":   prompt,
                "stream":   True,
                "keep_alive": -1,
                "options":  options
            },
            stream=True,
            timeout=120
        )

        for line in response.iter_lines():
            if stop_flag and stop_flag():
                response.close()
                break
            if line:
                data  = json.loads(line.decode("utf-8"))
                token = data.get("response", "")
                answer += token
                if chunk_callback and chunk_id:
                    chunk_callback("token", {"id": chunk_id, "text": label + answer})
                if data.get("done"):
                    gen_elapsed = round(time.time() - gen_start, 1)
                    if is_bad_response(answer):
                        final = label + "[bold yellow]⚠ Model couldn't answer from context[/bold yellow]"
                    else:
                        final = label + answer + f" [dim](generated in {gen_elapsed}s)[/dim]"
                    if chunk_callback and chunk_id:
                        chunk_callback("token", {"id": chunk_id, "text": final})
                    break

    except Exception as e:
        if not (stop_flag and stop_flag()):
            if chunk_callback:
                chunk_callback("token", {
                    "id":   chunk_id,
                    "text": label + f"[bold red]Error: {e}[/bold red]"
                })

    return answer

def is_relevant(text, query):
    stop_words = {
        "what", "is", "the", "a", "an", "of", "in", "on", "for",
        "to", "and", "or", "how", "why", "who", "when", "where",
        "list", "tell", "me", "about", "today", "latest", "news"
    }
    query_words = set(query.lower().split()) - stop_words
    text_lower = text.lower()
    return sum(1 for w in query_words if w in text_lower) >= 2

## ── scrape all selected links in parallel — 1 block per link ─────────────────

def scrape_all_links(links, progress, feed_size):
    results = []

    def scrape_one(link):
        text = scrape_text(link["url"], max_words=feed_size)
        return link, text

    with ThreadPoolExecutor(max_workers=min(5, len(links))) as executor:
        futures = {executor.submit(scrape_one, l): l for l in links}
        for future in as_completed(futures):
            link, text = future.result()
            if text:
                progress(
                    f"[dim green]  ✓ scraped {link['title'][:45]} "
                    f"({len(text.split())} words)[/dim green]"
                )
                results.append({
                    "link": link,
                    "content": text,
                    "word_count": len(text.split())
                })
            else:
                progress(
                    f"[dim yellow]  ⚠ could not scrape {link['title'][:45]}[/dim yellow]"
                )

    return results

## ── main pipeline ─────────────────────────────────────────────────────────────

def ask_localmind(query, max_links=MAX_LINKS, feed_size=3000,
                  progress_callback=None, chunk_callback=None,
                  stop_flag=None, model="mistral:latest"):

    def progress(msg):
        if progress_callback:
            progress_callback(msg)

    if not bridge.is_panel_alive():
        progress(
            "[bold red]⚠ Control panel is not running — "
            "open it with /panel[/bold red]"
        )
        return []

    ## ══ STEP 1 — query selection ══════════════════════════════════
    progress("[dim]🧠 Generating 3 search query variants...[/dim]")

    variants = generate_query_variants(query, model)

    bridge.prepare_for_result()
    bridge.write_state(
        step=bridge.STEP_QUERY_SELECT,
        data=[{"index": i+1, "query": v} for i, v in enumerate(variants)],
        meta={"status": "Waiting for query selection..."}
    )

    progress("[dim cyan]⏳ Waiting for query selection in control panel...[/dim cyan]")

    result = bridge.wait_for_result(timeout=120, stop_flag=stop_flag)
    if result is None:
        progress("[bold red]✗ No query selected — aborting[/bold red]")
        return []

    chosen_query = result.get("selected", query)
    progress(f"[dim green]✓ Query selected: {chosen_query}[/dim green]")

    if stop_flag and stop_flag():
        return []

    ## ══ STEP 2 — link selection ═══════════════════════════════════
    progress("[dim]🌐 Searching web...[/dim]")

    ddg_links = search_links(chosen_query, max_results=max_links)

    if not ddg_links:
        progress("[bold red]✗ No links found for this query[/bold red]")
        return []

    progress(f"[dim]✓ Found {len(ddg_links)} links[/dim]")

    bridge.prepare_for_result()
    bridge.write_state(
        step=bridge.STEP_LINK_SELECT,
        data=[
            {"index": i+1, "title": l["title"], "url": l["url"], "snippet": l.get("snippet", "")}
            for i, l in enumerate(ddg_links)
        ],
        meta={"status": "Waiting for link selection..."}
    )

    progress("[dim cyan]⏳ Waiting for link selection in control panel...[/dim cyan]")

    result = bridge.wait_for_result(timeout=120, stop_flag=stop_flag)
    if result is None:
        progress("[bold red]✗ No links selected — aborting[/bold red]")
        return []

    selected_indices = result.get("selected", [])
    selected_links   = [
        ddg_links[i-1] for i in selected_indices
        if 0 < i <= len(ddg_links)
    ]

    progress(f"[dim green]✓ {len(selected_links)} link(s) selected[/dim green]")

    if stop_flag and stop_flag() or not selected_links:
        return []

    ## ══ STEP 3 — scrape ALL selected links first ═══════════════════
    progress(f"[dim cyan]📥 Scraping {len(selected_links)} link(s) in parallel...[/dim cyan]")

    scraped = scrape_all_links(selected_links, progress, feed_size)

    if not scraped:
        progress("[bold red]✗ Could not scrape any of the selected links[/bold red]")
        return []

    progress(f"[dim green]✓ Successfully scraped {len(scraped)} link(s)[/dim green]")

    if stop_flag and stop_flag():
        return []

    ## ══ STEP 4 — show all scraped links, user picks which to generate from ══
    bridge.prepare_for_result()
    bridge.write_state(
        step=bridge.STEP_SECTION_SELECT,
        data=[
            {
                "index":      i+1,
                "title":      item["link"]["title"],
                "word_count": item["word_count"],
                "content":    item["content"][:300]  ## preview only in panel
            }
            for i, item in enumerate(scraped)
        ],
        meta={
            "site_title": f"{len(scraped)} scraped link(s)",
            "status": "Select which link(s) to generate response from — leave blank to skip"
        }
    )

    progress(
        "[dim cyan]⏳ Waiting for generation selection in control panel "
        "(select 0 to skip)...[/dim cyan]"
    )

    result = bridge.wait_for_result(timeout=120, stop_flag=stop_flag)
    if result is None:
        progress("[dim yellow]⏱ Timed out — no generation performed[/dim yellow]")
        return [item["link"]["title"] for item in scraped]

    selected_gen_indices = result.get("selected", [])

    if not selected_gen_indices:
        progress("[bold yellow]⏭ Generation skipped by user choice[/bold yellow]")
        bridge.write_state(
            step=bridge.STEP_DONE, data=[],
            meta={"status": "Skipped — no generation performed"}
        )
        return [item["link"]["title"] for item in scraped]

    chosen_items = [
        scraped[i-1] for i in selected_gen_indices
        if 0 < i <= len(scraped)
    ]

    ## ══ STEP 5 — generate from each chosen link ════════════════════
    sources = []

    bridge.write_state(
        step=bridge.STEP_GENERATING,
        data=[],
        meta={
            "sources": [item["link"]["title"] for item in chosen_items],
            "sections_count": len(chosen_items),
            "status": f"Generating from {len(chosen_items)} link(s)..."
        }
    )

    for item in chosen_items:
        if stop_flag and stop_flag():
            break

        link    = item["link"]
        content = item["content"]

        if not is_relevant(content, query):
            progress(f"[dim]⏭ skipping {link['title'][:40]} — not relevant[/dim]")
            continue

        progress(f"[dim cyan]🤖 Generating from {link['title'][:40]}...[/dim cyan]")

        sources.append(link["title"])

        label = f"[bold cyan]LocalMind[/bold cyan] [dim]({link['title'][:30]}):[/dim] "
        chunk_id = chunk_callback("start", label) if chunk_callback else None
        prompt   = build_prompt(query, content, link["title"], model)
        stream_to_model(prompt, chunk_callback, chunk_id, label, stop_flag, model)

        progress(f"[dim green]✓ Done with {link['title'][:30]}[/dim green]")

    bridge.write_state(
        step=bridge.STEP_DONE,
        data=[],
        meta={"status": f"Complete — generated from {len(sources)} source(s)"}
    )

    return sources