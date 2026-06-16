## File Name: pipeline.py
## Description: Main pipeline - AI decision maker + section picker + multi search
## Path: scripts/pipeline.py
## Created By: Lokesh R     Created On: 2026-05-19
## Updated By: Lokesh R     Updated On: 2026-06-16
## Added section picker, multi search, arXiv support, date awareness, feed size control

## Import - Libraries
import requests
import json
import time
from datetime import date, timedelta

## Import - Application Program Files
from search import search_links, search_wikipedia, search_arxiv, multi_search
from scraper import scrape_text, scrape_sections
from router import get_context

MAX_LINKS = 5
CHUNK_SIZE = 1500
TODAY       = date.today().strftime("%B %d, %Y")
TODAY_SHORT = date.today().strftime("%Y-%m-%d")
YESTERDAY   = (date.today() - timedelta(days=1)).strftime("%B %d, %Y")
YESTERDAY_SHORT = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
CURRENT_YEAR    = date.today().strftime("%Y")
CURRENT_MONTH   = date.today().strftime("%B %Y")

def get_model_options(model):
    model_lower = model.lower()
    if "tinyllama" in model_lower or ":1b" in model_lower:
        return {"num_predict": 256, "temperature": 0.1, "num_ctx": 1024}
    elif any(x in model_lower for x in ["3b", "phi", "gemma"]):
        return {"num_predict": 512, "temperature": 0.2, "num_ctx": 2048}
    else:
        return {"num_predict": 768, "temperature": 0.3, "num_ctx": 4096}

def is_bad_response(answer):
    bad_phrases = [
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
    return any(phrase in answer.lower() for phrase in bad_phrases)

def resolve_time_references(query):
    ## replace relative time words with actual dates so search engines find recent results
    q = query.lower()
    resolved = query

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
            resolved = resolved.lower().replace(word, replacement)
            break

    return resolved

def rewrite_query(query, model):
    ## resolve time references BEFORE sending to LLM
    time_resolved = resolve_time_references(query)

    prompt = f"""<system>
You are a search engine optimization backend. Convert raw user query into clean searchable keywords.
Today's date is {TODAY}. Yesterday was {YESTERDAY}.
RULES:
- Output ONLY keywords. No explanation.
- Keep intent identical.
- If query mentions yesterday/today/recent, include the actual date: {YESTERDAY_SHORT} or {TODAY_SHORT}
- Always include the year {CURRENT_YEAR} for sports/news/events queries.
- Never remove time context — it is critical.
</system>

User Query: "latest news on AI"
Optimized Keywords: latest artificial intelligence advancements news {CURRENT_YEAR}

User Query: "who won the ipl match in 2026 in india"
Optimized Keywords: 2026 Indian Premier League winner results

User Query: "who won yesterday's fifa match"
Optimized Keywords: FIFA match result {YESTERDAY_SHORT} winner

User Query: "{time_resolved}"
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
            return time_resolved
        return rewritten
    except:
        return time_resolved

def decide_search_strategy(query, model):
    prompt = f"""You are a search router. Decide the best way to answer this query.
Today's date is {TODAY}.

Options:
- rss: recent news, sports scores, finance updates, trending topics
- web: specific facts, history, how-to, research, general knowledge
- both: needs latest news AND detailed background
- arxiv: academic research, scientific papers, AI/ML papers
- local: simple conversation, math, greetings, basic questions

Reply with ONLY one word: rss, web, both, arxiv, or local

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
        if decision not in ["rss", "web", "both", "arxiv", "local"]:
            return "web"
        return decision
    except:
        return "web"

def build_prompt(query, context, source_title, chunk_index, total_chunks, model):
    model_lower = model.lower()
    date_ctx = f"Today is {TODAY}. Yesterday was {YESTERDAY}. Current year is {CURRENT_YEAR}.\n"

    system = (
        f"IMPORTANT: You have been given LIVE scraped data from the internet. "
        f"{date_ctx}"
        f"You MUST answer using ONLY the text below. "
        f"Do NOT say you cannot access the internet — you already have the data. "
        f"Do NOT mention your training cutoff. "
        f"If the answer is in the text, state it directly and confidently.\n\n"
    )

    if "tinyllama" in model_lower or ":1b" in model_lower:
        return system + f"Source: {source_title}\nText: {context}\nQuestion: {query}\nAnswer:"

    elif any(x in model_lower for x in ["3b", "phi", "gemma"]):
        return (
            system +
            f"=== LIVE DATA FROM {source_title.upper()} ===\n"
            f"{context}\n"
            f"=== END OF DATA ===\n\n"
            f"Based on the data above, answer this question directly:\n"
            f"Question: {query}\n"
            f"Answer (use only the data above, be specific):"
        )

    else:
        return (
            system +
            f"Chunk {chunk_index}/{total_chunks} from \"{source_title}\":\n"
            f"{context}\n\n"
            f"Question: {query}\n"
            f"Detailed answer:"
        )

def build_rss_prompt(query, context, model):
    model_lower = model.lower()
    date_ctx = f"Today is {TODAY}. Yesterday was {YESTERDAY}. Current year is {CURRENT_YEAR}.\n"

    if not context:
        return f"{date_ctx}Answer this question directly:\n{query}"

    system = (
        f"IMPORTANT: The data below was LIVE FETCHED from trusted news sources right now. "
        f"{date_ctx}"
        f"You MUST use ONLY this data to answer. "
        f"Do NOT say you cannot access the internet — this data was already fetched for you. "
        f"Do NOT mention training cutoff or knowledge limits. "
        f"Answer directly and confidently from the data.\n\n"
    )

    if "tinyllama" in model_lower or ":1b" in model_lower:
        return system + f"Data:\n{context[:2000]}\nQuestion: {query}\nAnswer:"

    elif any(x in model_lower for x in ["3b", "phi", "gemma"]):
        return (
            system +
            f"=== LIVE FETCHED DATA ===\n"
            f"{context[:3000]}\n"
            f"=== END OF DATA ===\n\n"
            f"Question: {query}\n"
            f"Answer (be specific, cite teams/scores/names from the data above):"
        )

    else:
        return system + f"Data:\n{context[:4000]}\n\nQuestion: {query}\nAnswer:"

def chunk_text(text, chunk_size=CHUNK_SIZE):
    ## FIX: chunk_size now configurable via feed_size from localmind.py
    words = text.split()
    chunks = []
    current = []
    current_len = 0
    for word in words:
        current_len += len(word) + 1
        current.append(word)
        if current_len >= chunk_size:
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
            stream=True,
            timeout=120
        )

        for line in response.iter_lines():
            if stop_flag and stop_flag():
                response.close()  ## force-close so iter_lines unblocks immediately
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
        if not (stop_flag and stop_flag()):  ## don't show error if we stopped intentionally
            if chunk_callback:
                chunk_callback("token", {"id": chunk_id, "text": label + f"[bold red]Error: {e}[/bold red]"})

    return answer

def process_result_with_sections(link, query, model, chunk_callback, stop_flag,
                                  progress_callback, sources, feed_size=CHUNK_SIZE,
                                  section_picker_callback=None):
    ## scrape sections from this page
    sections = scrape_sections(link["url"])

    if not sections:
        ## fallback to normal scraping
        text = scrape_text(link["url"])
        if not text:
            return
        sources.append(link["title"])
        sources.append(link["url"])
        chunks = chunk_text(text, chunk_size=feed_size)

        if progress_callback:
            progress_callback(f"[dim green]  ✓ scraped {link['title'][:40]} → {len(chunks)} chunks[/dim green]")

        for chunk_index, chunk in enumerate(chunks):
            if stop_flag and stop_flag():
                break
            if not is_relevant(chunk, query):
                if progress_callback:
                    progress_callback(f"[dim]  ⏭ skipping chunk {chunk_index+1}/{len(chunks)} — not relevant[/dim]")
                continue
            if progress_callback:
                progress_callback(f"[dim]  📤 feeding chunk {chunk_index+1}/{len(chunks)}...[/dim]")
            label = f"[bold cyan]LocalMind[/bold cyan] [dim]({link['title'][:25]} · chunk {chunk_index+1}/{len(chunks)}):[/dim] "
            chunk_id = chunk_callback("start", label) if chunk_callback else None
            prompt = build_prompt(query, chunk, link["title"], chunk_index+1, len(chunks), model)
            stream_to_mistral(prompt, chunk_callback, chunk_id, label, stop_flag, model)
        return

    sources.append(link["title"])
    sources.append(link["url"])

    if progress_callback:
        progress_callback(f"[dim green]  ✓ scraped {link['title'][:40]} → {len(sections)} sections[/dim green]")

    ## show sections to user via callback
    if section_picker_callback:
        selected = section_picker_callback(link["title"], sections)
        if selected:
            sections = [s for s in sections if s["index"] in selected]

    ## feed selected sections
    for section in sections:
        if stop_flag and stop_flag():
            break
        if not is_relevant(section["content"], query):
            if progress_callback:
                progress_callback(f"[dim]  ⏭ skipping [{section['index']}] {section['title'][:30]} — not relevant[/dim]")
            continue
        if progress_callback:
            progress_callback(f"[dim]  📤 feeding [{section['index']}] {section['title'][:40]}...[/dim]")
        label = f"[bold cyan]LocalMind[/bold cyan] [dim]({link['title'][:20]} › {section['title'][:20]}):[/dim] "
        chunk_id = chunk_callback("start", label) if chunk_callback else None
        prompt = build_prompt(query, section["content"], f"{link['title']} — {section['title']}", 1, 1, model)
        stream_to_mistral(prompt, chunk_callback, chunk_id, label, stop_flag, model)

def ask_localmind(query, max_links=MAX_LINKS, feed_size=CHUNK_SIZE, progress_callback=None,
                  chunk_callback=None, stop_flag=None, model="mistral:latest",
                  section_picker_callback=None):

    ## step 0 — rewrite query with time resolution
    if progress_callback:
        progress_callback("[dim]🧠 Understanding query...[/dim]")

    rewritten = rewrite_query(query, model)
    if rewritten != query and progress_callback:
        progress_callback(f"[dim cyan]🧠 Searching for: {rewritten}[/dim cyan]")

    search_query = rewritten

    ## step 1 — AI decides strategy
    strategy = decide_search_strategy(query, model)
    if progress_callback:
        labels = {
            "rss":   "📡 Using trusted sources",
            "web":   "🌐 Searching the web",
            "both":  "📡🌐 Using RSS + web search",
            "arxiv": "📚 Searching research papers",
            "local": "🤖 Answering from knowledge"
        }
        progress_callback(f"[dim cyan]{labels.get(strategy, '🌐 Searching')}...[/dim cyan]")

    ## step 2 — local
    if strategy == "local":
        label = "[bold cyan]LocalMind[/bold cyan] [dim](local knowledge):[/dim] "
        chunk_id = chunk_callback("start", label) if chunk_callback else None
        prompt = build_rss_prompt(query, "", model)
        stream_to_mistral(prompt, chunk_callback, chunk_id, label, stop_flag, model)
        return []

    ## step 3 — arXiv
    if strategy == "arxiv":
        if progress_callback:
            progress_callback("[dim cyan]📚 Searching arXiv research papers...[/dim cyan]")
        arxiv_results = search_arxiv(search_query, max_results=3)
        if arxiv_results:
            context = "Research papers from arXiv:\n\n"
            for r in arxiv_results:
                context += f"Title: {r['title']}\n"
                context += f"Content: {r['content']}\n\n"
                if progress_callback:
                    progress_callback(f"[dim green]  ✓ paper: {r['title'][:50]}[/dim green]")
            label = "[bold cyan]LocalMind[/bold cyan] [dim](via arXiv):[/dim] "
            chunk_id = chunk_callback("start", label) if chunk_callback else None
            prompt = build_rss_prompt(query, context, model)
            stream_to_mistral(prompt, chunk_callback, chunk_id, label, stop_flag, model)
            return []

    rss_answer = ""

    ## step 4 — RSS trusted sources
    if strategy in ["rss", "both"]:
        context, category = get_context(search_query, progress_callback=progress_callback)
        if context:
            if progress_callback:
                progress_callback(f"[dim cyan]📡 {category.upper()} — using trusted sources...[/dim cyan]")
            label = f"[bold cyan]LocalMind[/bold cyan] [dim](via {category}):[/dim] "
            chunk_id = chunk_callback("start", label) if chunk_callback else None
            prompt = build_rss_prompt(query, context, model)
            rss_answer = stream_to_mistral(prompt, chunk_callback, chunk_id, label, stop_flag, model)
            if strategy == "rss":
                return []
            if not is_bad_response(rss_answer):
                return []
            if progress_callback:
                progress_callback("[dim yellow]📡 Not enough — also searching web...[/dim yellow]")

    ## step 5 — web search with Wikipedia + DuckDuckGo
    if progress_callback:
        progress_callback("[dim cyan]🌐 Searching the web...[/dim cyan]")

    wiki_results = search_wikipedia(search_query, max_results=2)
    if wiki_results and progress_callback:
        progress_callback(f"[dim]✓ Found {len(wiki_results)} Wikipedia articles[/dim]")

    ddg_links = search_links(search_query, max_results=max_links)
    if progress_callback:
        progress_callback(f"[dim]✓ Found {len(ddg_links)} web links[/dim]")

    sources = []

    ## process Wikipedia results first (already clean text)
    for wiki in wiki_results:
        if stop_flag and stop_flag():
            break
        if progress_callback:
            progress_callback(f"[dim]→ Wikipedia: {wiki['title'][:50]}[/dim]")
        content = wiki.get("content", "")
        if not content:
            continue
        sources.append(wiki["title"])
        sources.append(wiki["url"])
        chunks = chunk_text(content, chunk_size=feed_size)
        if progress_callback:
            progress_callback(f"[dim green]  ✓ {wiki['title'][:40]} → {len(chunks)} chunks[/dim green]")
        for chunk_index, chunk in enumerate(chunks):
            if stop_flag and stop_flag():
                break
            if not is_relevant(chunk, query):
                if progress_callback:
                    progress_callback(f"[dim]  ⏭ skipping chunk {chunk_index+1}/{len(chunks)}[/dim]")
                continue
            if progress_callback:
                progress_callback(f"[dim]  📤 feeding chunk {chunk_index+1}/{len(chunks)}...[/dim]")
            label = f"[bold cyan]LocalMind[/bold cyan] [dim](Wikipedia: {wiki['title'][:20]} · chunk {chunk_index+1}/{len(chunks)}):[/dim] "
            chunk_id = chunk_callback("start", label) if chunk_callback else None
            prompt = build_prompt(query, chunk, wiki["title"], chunk_index+1, len(chunks), model)
            stream_to_mistral(prompt, chunk_callback, chunk_id, label, stop_flag, model)

    ## process DuckDuckGo links with section picker
    for site_index, link in enumerate(ddg_links):
        if stop_flag and stop_flag():
            break
        if progress_callback:
            progress_callback(f"[dim]→ [{site_index+1}/{len(ddg_links)}] visiting {link['url'][:60]}...[/dim]")
        process_result_with_sections(
            link, query, model, chunk_callback, stop_flag,
            progress_callback, sources,
            feed_size=feed_size,
            section_picker_callback=section_picker_callback
        )

    return sources