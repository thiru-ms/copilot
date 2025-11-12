import os, json, requests
AZURE_OPENAI_ENDPOINT   = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY    = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT","gpt-5-mini")

def classify_with_citations(query, articles):
    if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
        return {"classification":"Unclear","rationale":"LLM not configured.","citations":[]}
    sys = ("You are a careful fact-checking assistant for Grade-9 students. "
           "Use ONLY the provided articles. If evidence is mixed/insufficient, answer 'Unclear'. "
           "Always include 2–4 citations (title, source, url). Neutral tone.")
    evidence="\n\n".join([f"- Title: {a['title']}\n  Source: {a['source']}\n  URL: {a['url']}\n  Snippet: {a.get('snippet','')}" for a in articles])
    usr = f"""Claim or headline:
\"\"\"{query}\"\"\"

Articles:
{evidence}

Task:
Return JSON with:
  classification: "Supported" | "Contradicted" | "Unclear"
  rationale: <= 6 sentences; reference article titles
  citations: array of {{title, source, url}}
Use ONLY the articles above."""
    url=f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version=2024-10-01-preview"
    headers={"api-key":AZURE_OPENAI_API_KEY,"Content-Type":"application/json"}
    body={"messages":[{"role":"system","content":sys},{"role":"user","content":usr}],
          "temperature":0.2,"response_format":{"type":"json_object"}}
    r=requests.post(url,headers=headers,json=body,timeout=30); r.raise_for_status()
    content=r.json()["choices"][0]["message"]["content"]
    return json.loads(content)