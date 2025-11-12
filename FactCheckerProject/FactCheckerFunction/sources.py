import os, re, requests

GUARDIAN_KEY = os.getenv("GUARDIAN_API_KEY")
NEWS_KEY = os.getenv("NEWSAPI_KEY")

TRUSTED = {"apnews.com","reuters.com","bbc.co.uk","bbc.com",
           "thehindu.com","indianexpress.com","hindustantimes.com",
           "theguardian.com","nytimes.com"}

def _domain(u): return re.sub(r"^https?://(www\.)?","",u or "").split("/")[0].lower()
def _trusted(u): 
    d=_domain(u); return any(d.endswith(t) or t.endswith(d) for t in TRUSTED)

def fetch_guardian(q, frm=None, to=None, page_size=10):
    if not GUARDIAN_KEY: return []
    url = "https://content.guardianapis.com/search"
    params = {"q": q, "api-key": GUARDIAN_KEY, "page-size": page_size,
              "order-by": "relevance", "show-fields":"headline,trailText,short-url"}
    if frm: params["from-date"]=frm
    if to:  params["to-date"]=to
    r = requests.get(url, params=params, timeout=12); r.raise_for_status()
    out=[]
    for it in r.json().get("response", {}).get("results", []):
        u = it.get("webUrl")
        out.append({"title":it.get("webTitle","").strip(),"url":u,"source":"The Guardian",
                    "snippet":(it.get("fields",{}) or {}).get("trailText",""),
                    "publishedAt":it.get("webPublicationDate"),"trusted":_trusted(u)})
    return out

def fetch_newsapi(q, frm=None, to=None, page_size=20, language="en"):
    if not NEWS_KEY: return []
    base="https://newsapi.org/v2/everything"
    params={"q":q,"apiKey":NEWS_KEY,"pageSize":page_size,"language":language,"sortBy":"relevancy"}
    if frm: params["from"]=frm
    if to:  params["to"]=to
    r = requests.get(base, params=params, timeout=12)
    out=[]
    if r.status_code==200:
        for a in r.json().get("articles", []):
            u=a.get("url")
            out.append({"title":a.get("title","").strip(),"url":u,
                        "source":(a.get("source") or {}).get("name",""),
                        "snippet":a.get("description",""),
                        "publishedAt":a.get("publishedAt"),"trusted":_trusted(u)})
        return out
    # fallback to top-headlines if everything is restricted
    base="https://newsapi.org/v2/top-headlines"
    params={"q":q,"apiKey":NEWS_KEY,"pageSize":page_size,"language":language}
    r=requests.get(base, params=params, timeout=12); r.raise_for_status()
    for a in r.json().get("articles", []):
        u=a.get("url")
        out.append({"title":a.get("title","").strip(),"url":u,
                    "source":(a.get("source") or {}).get("name",""),
                    "snippet":a.get("description",""),
                    "publishedAt":a.get("publishedAt"),"trusted":_trusted(u)})
    return out

def search_all(q, frm=None, to=None, limit=12):
    seen=set(); merged=[]
    for a in (fetch_guardian(q, frm, to, min(10,limit)) + fetch_newsapi(q, frm, to, min(20,limit*2))):
        u=a.get("url"); 
        if not u or u in seen: continue
        seen.add(u); merged.append(a)
    merged.sort(key=lambda x: (not x["trusted"], (x["publishedAt"] or "")))
    return merged[:limit]