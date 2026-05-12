import requests

def search_wikipedia(query):
    formatted_query = query.replace(" ","_")

    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{formatted_query}"

    headers ={
        "User-Agent":"LocalMind/1.0 (lokeshrmt09.mt10@gmail.com)"
    }

    response = requests.get(url,headers=headers)


    if response.status_code!=200:
        return f"Error : WiKipedia returns {response.status_code}"
    data = response.json()

    clean_text = data["extract"]

    return clean_text

def ask_localmind(query):
    print(f"Searching wiki for {query}")
    context = search_wikipedia(query)

    prompt = f"""You are a research assistant.
    Only use the context below to answer the question.
    Do not add anything from your own knowledge.

    Context:
    {context}

    Question:
    {query}

    Answer in clear simple language:"""

    print("Sending to Mistral...")
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "mistral",
            "prompt": prompt,
            "stream": False
        }
    )

    return response.json()["response"]

if __name__ == "__main__":
    answer = ask_localmind("What is the Hantavirus?")
    print("\n--- LocalMind Answer ---")
    print(answer)