import requests

response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "mistral",
        "prompt": "Summarize this in 3 lines: The Mariana Trench is the deepest part of the world's oceans. It is located in the western Pacific Ocean. Its deepest point is called Challenger Deep.",
        "stream": False
    }
)

print(response.json()["response"])