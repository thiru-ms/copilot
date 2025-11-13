import logging
import json, azure.functions as func
from binggrounding import get_response_and_classify
from newsapisearch import classify_with_newsdata
from sources import search_all
from factcheck_llm import classify_with_citations
from datetime import datetime, timedelta
from urllib.parse import quote

app = func.FunctionApp()

@app.function_name(name="FactCheckHttpBing")   # First function
@app.route(route="factcheckbing", auth_level=func.AuthLevel.ANONYMOUS)
def function_app1(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processing a request.')
    try:
        raw_body = req.get_body().decode('utf-8')
        body = json.loads(raw_body)
        query = body.get("query")
        q = quote(query, safe='')
        frm = body.get("from")
        to  = body.get("to")
        
        today = datetime.today().date()
        if not to:
            to = today.strftime("%Y-%m-%d")
        if not frm:
            frm = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        if not q:
            return func.HttpResponse(json.dumps({"error":"query required"}), status_code=400)
        
        logging.info(f'{q}, {frm}, {to}')
        payload = get_response_and_classify(q)

        logging.info(f'response: {json.dumps(payload)}')
        return func.HttpResponse(json.dumps(payload), status_code=200, mimetype="application/json")

        # arts = search_all(q, frm=frm, to=to, limit=12)
        # logging.info(f'{arts}')
        # res  = classify_with_citations(q, arts)
        # payload = {
        #     "classification": res.get("classification","Unclear"),
        #     "rationale":      res.get("rationale",""),
        #     "citations":      res.get("citations", []),
        #     "articles": [{"title":a["title"],"source":a["source"],"url":a["url"],"trusted":a["trusted"]} for a in arts]
        # }
        # logging.info(f'response: {json.dumps(payload)}')
        # return func.HttpResponse(json.dumps(payload), status_code=200, mimetype="application/json")
    except Exception as e:
        logging.info(f'response: {e}')
        return func.HttpResponse(json.dumps({"error":str(e)}), status_code=500)

@app.function_name(name="FactCheckHttpNewsDataIo")   # First function
@app.route(route="factchecknewsdataio", auth_level=func.AuthLevel.ANONYMOUS)
def function_app2(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processing a request.')
    try:
        raw_body = req.get_body().decode('utf-8')
        logging.info(f'Raw body: {raw_body}')
        body = json.loads(raw_body)
        logging.info(f'{body}')
        query   = body.get("query")
        q = quote(query, safe='')
        frm = body.get("from")
        to  = body.get("to")
        
        today = datetime.today().date()
        if not to:
            to = today.strftime("%Y-%m-%d")
        if not frm:
            frm = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        if not q:
            return func.HttpResponse(json.dumps({"error":"query required"}), status_code=400)
        
        logging.info(f'{q}, {frm}, {to}')

        payload = classify_with_newsdata(
            query=q,
            country="in",
            language="en",
            page_limit=2,          # fetch up to 2 pages
            use_sdk=False,         # set True if you installed `newsdataapi`
        )

        logging.info(f'response: {json.dumps(payload)}')
        return func.HttpResponse(json.dumps(payload), status_code=200, mimetype="application/json")

        # arts = search_all(q, frm=frm, to=to, limit=12)
        # logging.info(f'{arts}')
        # res  = classify_with_citations(q, arts)
        # payload = {
        #     "classification": res.get("classification","Unclear"),
        #     "rationale":      res.get("rationale",""),
        #     "citations":      res.get("citations", []),
        #     "articles": [{"title":a["title"],"source":a["source"],"url":a["url"],"trusted":a["trusted"]} for a in arts]
        # }
        # logging.info(f'response: {json.dumps(payload)}')
        # return func.HttpResponse(json.dumps(payload), status_code=200, mimetype="application/json")
    except Exception as e:
        logging.info(f'response: {e}')
        return func.HttpResponse(json.dumps({"error":str(e)}), status_code=500)