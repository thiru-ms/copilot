import logging
import json, azure.functions as func
from sources import search_all
from factcheck_llm import classify_with_citations
from datetime import datetime, timedelta

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="function_app", auth_level=func.AuthLevel.ANONYMOUS)
def function_app(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processing a request.')
    try:
        body = req.get_json()
        q   = body.get("query")
        frm = body.get("from")
        to  = body.get("to")
        today = datetime.today().date()
        if not to:
            to = today.strftime("%Y-%m-%d")
        if not frm:
            frm = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        if not q:
            return func.HttpResponse(json.dumps({"error":"query required"}), status_code=400)
        arts = search_all(q, frm=frm, to=to, limit=12)
        res  = classify_with_citations(q, arts)
        payload = {
            "classification": res.get("classification","Unclear"),
            "rationale":      res.get("rationale",""),
            "citations":      res.get("citations", []),
            "articles": [{"title":a["title"],"source":a["source"],"url":a["url"],"trusted":a["trusted"]} for a in arts]
        }
        return func.HttpResponse(json.dumps(payload), status_code=200, mimetype="application/json")
    except Exception as e:
        return func.HttpResponse(json.dumps({"error":str(e)}), status_code=500)

@app.route(route="FactCheckHttp", auth_level=func.AuthLevel.ANONYMOUS)
def FactCheckHttp(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    name = req.params.get('name')
    if not name:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            name = req_body.get('name')

    if name:
        return func.HttpResponse(f"Hello, {name}. This HTTP triggered function executed successfully.")
    else:
        return func.HttpResponse(
             "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
             status_code=200
        )

@app.route(route="FactCheckHttp", auth_level=func.AuthLevel.ANONYMOUS)
def FactCheckHttp(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    name = req.params.get('name')
    if not name:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            name = req_body.get('name')

    if name:
        return func.HttpResponse(f"Hello, {name}. This HTTP triggered function executed successfully.")
    else:
        return func.HttpResponse(
             "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
             status_code=200
        )