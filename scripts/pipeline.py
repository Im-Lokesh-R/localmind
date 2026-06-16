## File Name: pipeline.py
## Description: Human-in-the-loop pipeline — every step gated by control panel
## Path: scripts/pipeline.py
## Created By: Lokesh R     Created On: 2026-05-19
## Updated By: Lokesh R     Updated On: 2026-06-16

import requests
import json
import time
from datetime import date, timedelta

from search import search_links, search_wikipedia, search_arxiv
from scraper import scrape_text, scrape_sections
import panel_bridge as bridge

MAX_LINKS  = 5
CHUNK_SIZE = 1500
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
        raw = response.json().get("response", "").strip()
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        ## take first 3 non-empty lines
        variants = lines[:3]
        ## pad to 3 if model returned fewer
        while len(variants) < 3:
            variants.append(time_resolved)
        return variants[:3]
    except:
        return [time_resolved, time_resolved, time_resolved]

## ── step 2: search ────────────────────────────────────────────────────────────

def run_search(query, max_links, progress_callback):
    if progress_callback:
        progress_callback("[dim]🌐 Searching the web...[/dim]")

    ddg_links = search_links(query, max_results=max_links)

    if progress_callback:
        progress_callback(f"[dim]✓ Found {len(ddg_links)} links[/dim]")

    return ddg_links

## ── prompt builders ───────────────────────────────────────────────────────────

def build_prompt(query, context, source_title, chunk_index, total_chunks, model):
    m = model.lower()
    date_ctx = f"Today is {TODAY}. Yesterday was {YESTERDAY}. Year: {CURRENT_YEAR}.\n"
    system = (
        f"IMPORTANT: You have LIVE scraped data from the internet. {date_ctx}"
        f"Answer using ONLY the text below. "
        f"Do NOT mention training cutoff or inability to access internet. "
        f"If the answer is in the text, state it directly and confidently.\n\n"
    )
    if "tinyllama" in m or ":1b" in m:
        return system + f"Source: {source_title}\nText: {context}\nQuestion: {query}\nAnswer:"
    elif any(x in m for x in ["3b", "phi", "gemma"]):
        return (
            system +
            f"=== LIVE DATA FROM {source_title.upper()} ===\n{context}\n=== END ===\n\n"
            f"Question: {query}\nAnswer (specific, from data above):"
        )
    else:
        return (
            system +
            f"Chunk {chunk_index}/{total_chunks} from \"{source_title}\":\n{context}\n\n"
            f"Question: {query}\nDetailed answer:"
        )

## ── streaming ─────────────────────────────────────────────────────────────────

def stream_to_model(prompt, chunk_callback, chunk_id, label, stop_flag, model):
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
            stream=True,
            timeout=120
        )

        for line in response.iter_lines():
            if stop_flag and stop_flag():
                response.close()
                break
            if line:
                data = json.loads(line.decode("utf-8"))
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
                chunk_callback("token", {"id": chunk_id,
                    "text": label + f"[bold red]Error: {e}[/bold red]"})

    return answer

## ── chunk helpers ─────────────────────────────────────────────────────────────

def chunk_text(text, chunk_size=CHUNK_SIZE):
    words = text.split()
    chunks, current, current_len = [], [], 0
    for word in words:
        current_len += len(word) + 1
        current.append(word)
        if current_len >= chunk_size:
            chunks.append(" ".join(current))
            current, current_len = [], 0
    if current:
        chunks.append(" ".join(current))
    return chunks

def is_relevant(chunk, query):
    stop_words = {"what", "is", "the", "a", "an", "of", "in", "on", "for",
                  "to", "and", "or", "how", "why", "who", "when", "where",
                  "list", "tell", "me", "about", "today", "latest", "news"}
    query_words = set(query.lower().split()) - stop_words
    chunk_lower = chunk.lower()
    return sum(1 for w in query_words if w in chunk_lower) >= 2

## ── main pipeline ─────────────────────────────────────────────────────────────

def ask_localmind(query, max_links=MAX_LINKS, feed_size=CHUNK_SIZE,
                  progress_callback=None, chunk_callback=None,
                  stop_flag=None, model="mistral:latest"):

    def progress(msg):
        if progress_callback:
            progress_callback(msg)

    ## ── check panel is alive ──────────────────────────────────────
    if not bridge.is_panel_alive():
        progress("[bold red]⚠ Control panel is not running — open it with /panel[/bold red]")
        return []

    ## ══ STEP 1 — query selection ══════════════════════════════════
    progress("[dim]🧠 Generating 3 search query variants...[/dim]")

    variants = generate_query_variants(query, model)

    bridge.write_state(
        step=bridge.STEP_QUERY_SELECT,
        data=[
            {"index": i+1, "query": v}
            for i, v in enumerate(variants)
        ],
        instruction=None,  ## panel uses its own INSTRUCTIONS dict
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

    bridge.write_state(
        step=bridge.STEP_LINK_SELECT,
        data=[
            {
                "index":   i+1,
                "title":   l["title"],
                "url":     l["url"],
                "snippet": l.get("snippet", "")
            }
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
    selected_links   = [ddg_links[i-1] for i in selected_indices if 0 < i <= len(ddg_links)]
    progress(f"[dim green]✓ {len(selected_links)} link(s) selected[/dim green]")

    if stop_flag and stop_flag():
        return []

    ## ══ STEP 3 — scrape + section selection ══════════════════════
    sources         = []
    all_sections    = []  ## (link, section) pairs to feed

    for site_index, link in enumerate(selected_links):
        if stop_flag and stop_flag():
            break

        progress(
            f"[dim]→ [{site_index+1}/{len(selected_links)}] "
            f"scraping {link['url'][:60]}...[/dim]"
        )

        sections = scrape_sections(link["url"])

        if not sections:
            ## fallback — scrape as plain text and make one section
            text = scrape_text(link["url"])
            if text:
                sections = [{
                    "index": 1,
                    "title": "Full Content",
                    "content": text,
                    "word_count": len(text.split())
                }]
            else:
                progress(f"[dim yellow]  ⚠ Could not scrape {link['url'][:50]}[/dim yellow]")
                continue

        progress(
            f"[dim green]  ✓ scraped {link['title'][:40]} "
            f"→ {len(sections)} sections[/dim green]"
        )

        bridge.write_state(
            step=bridge.STEP_SECTION_SELECT,
            data=sections,
            meta={
                "site_title": link["title"],
                "site_url":   link["url"],
                "status":     f"Waiting for section selection ({site_index+1}/{len(selected_links)})..."
            }
        )

        progress(
            f"[dim cyan]⏳ Waiting for section selection "
            f"({site_index+1}/{len(selected_links)})...[/dim cyan]"
        )

        result = bridge.wait_for_result(timeout=120, stop_flag=stop_flag)
        if result is None:
            progress("[dim yellow]  ⏱ Timed out — skipping this page[/dim yellow]")
            continue

        selected_section_indices = result.get("selected", [])

        if selected_section_indices:
            chosen_sections = [
                s for s in sections
                if s["index"] in selected_section_indices
            ]
        else:
            chosen_sections = sections  ## all

        sources.append(link["title"])
        for s in chosen_sections:
            all_sections.append((link, s))

        progress(
            f"[dim green]  ✓ {len(chosen_sections)} section(s) selected "
            f"from {link['title'][:30]}[/dim green]"
        )

    if not all_sections:
        progress("[bold red]✗ No sections selected across any page — aborting[/bold red]")
        return sources

    if stop_flag and stop_flag():
        return sources

    ## ══ STEP 4 — generation ═══════════════════════════════════════
    bridge.write_state(
        step=bridge.STEP_GENERATING,
        data=[],
        meta={
            "sources":        sources,
            "sections_count": len(all_sections),
            "status":         "Generating — check main window for output"
        }
    )

    progress(
        f"[dim cyan]🤖 Generating from {len(all_sections)} section(s) "
        f"across {len(sources)} source(s)...[/dim cyan]"
    )

    for link, section in all_sections:
        if stop_flag and stop_flag():
            break

        if not is_relevant(section["content"], query):
            progress(
                f"[dim]  ⏭ skipping [{section['index']}] "
                f"{section['title'][:30]} — not relevant[/dim]"
            )
            continue

        progress(
            f"[dim]  📤 feeding [{section['index']}] "
            f"{section['title'][:40]}...[/dim]"
        )

        label = (
            f"[bold cyan]LocalMind[/bold cyan] "
            f"[dim]({link['title'][:20]} › {section['title'][:20]}):[/dim] "
        )
        chunk_id = chunk_callback("start", label) if chunk_callback else None
        prompt   = build_prompt(
            query, section["content"],
            f"{link['title']} — {section['title']}",
            1, 1, model
        )
        stream_to_model(prompt, chunk_callback, chunk_id, label, stop_flag, model)

    ## signal done
    bridge.write_state(
        step=bridge.STEP_DONE,
        data=[],
        meta={"status": "Response complete"}
    )

    return sources