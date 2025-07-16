from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
import pandas as pd
from fastapi.staticfiles import StaticFiles
import markdown2
import re
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import PlainTextResponse
from slowapi.middleware import SlowAPIMiddleware
from fastapi.templating import Jinja2Templates
from fastapi import Request
import html
from search_helpers import search_markdown_dataframe

app = FastAPI()

# Set up rate limiter: 10 requests per minute per IP
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request, exc):
    return PlainTextResponse("Rate limit exceeded. Please try again later.", status_code=429)

markdown_texts_df = pd.read_csv('data/markdown_texts.tsv', sep='\t')
agenda_items_df = pd.read_csv('data/agenda_items.tsv', sep='\t')

app.mount('/static', StaticFiles(directory='static'), name='static')

templates = Jinja2Templates(directory="templates")


# Update the form action on the home page to point to /search
@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/search", response_class=HTMLResponse)
@limiter.limit("10/minute")
def search_results(request: Request, text: str = Query(..., description="Keyword to search")):
    results = search_markdown_dataframe(markdown_texts_df, text)
    return templates.TemplateResponse(
        "search_results.html",
        {
            "request": request,
            "results": results,
            "query": text,
            "num_results": len(results)
        }
    )

@app.get("/full/{ds_id}", response_class=HTMLResponse)
def full_markdown(request: Request, ds_id: str):
    row = markdown_texts_df[markdown_texts_df['ds'] == ds_id]
    if row.empty:
        return HTMLResponse("<h2>Document not found</h2>", status_code=404)
    markdown_text = row.iloc[0]['markdown_text']
    markdown_html = markdown2.markdown(markdown_text)
    markdown_html = re.sub(r'<a ', '<a target=\"_blank\" rel=\"noopener noreferrer\" ', markdown_html)
    return templates.TemplateResponse(
        "full_markdown.html",
        {"request": request, "ds": ds_id, "markdown_html": markdown_html}
    )

@app.get("/analytics", response_class=HTMLResponse)
def explore(request: Request, agg: str = Query('application_type', description="Column to aggregate")):
    # Only allow aggregations on certain columns
    allowed_aggs = ['application_type', 'business_name', 'business_address']
    if agg not in allowed_aggs:
        agg = 'application_type'
    counts = agenda_items_df[agg].value_counts().sort_values(ascending=False)
    counts = counts.reset_index()
    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "agg": agg,
            "counts": counts.to_dict(orient='records'),
            "allowed_aggs": allowed_aggs
        }
    )

@app.get("/map", response_class=HTMLResponse)
def explore_map(request: Request, 
                ds_start: str = Query(None, description="Start ds (inclusive)"),
                ds_end: str = Query(None, description="End ds (inclusive)"),
                application_type: list[str] = Query(None, description="Application types to filter")):
    # Drop rows with missing coordinates
    map_df = agenda_items_df.dropna(subset=["latitude", "longitude"])
    # Filter by ds range if provided
    if ds_start:
        map_df = map_df[map_df["ds"] >= ds_start]
    if ds_end:
        map_df = map_df[map_df["ds"] <= ds_end]
    # Filter by application_type if provided
    if application_type:
        map_df = map_df[map_df["application_type"].isin(application_type)]
    # Join with markdown_texts_df on markdown_path to get markdown_text
    merged_df = map_df.merge(markdown_texts_df[["markdown_path", "ds"]], on="markdown_path", how="left", suffixes=("", "_md"))
    # Prepare data for the map: list of dicts with lat, lon, agenda item info, and markdown link
    pins = []
    for _, row in merged_df.iterrows():
        markdown_url = f"/full/{row['ds_md']}" if pd.notnull(row['ds_md']) else None
        info = f"{row['application_name']}<br>{row['business_name']}<br>{row['business_address']}<br>{row['application_type']}"
        if markdown_url:
            info += f'<br><a href=\"{markdown_url}\" target=\"_blank\">View Markdown</a>'
        pins.append({
            "lat": row["latitude"],
            "lon": row["longitude"],
            "info": info
        })
    # For filter UI: get all unique application_types and ds min/max
    all_application_types = sorted(agenda_items_df["application_type"].dropna().unique())
    ds_min = str(agenda_items_df["ds"].min())
    ds_max = str(agenda_items_df["ds"].max())
    return templates.TemplateResponse(
        "map.html",
        {
            "request": request,
            "pins": pins,
            "center_lat": 40.685904,
            "center_lon": -73.972179,
            "all_application_types": all_application_types,
            "selected_application_types": application_type or [],
            "ds_min": ds_min,
            "ds_max": ds_max,
            "ds_start": ds_start or ds_min,
            "ds_end": ds_end or ds_max
        }
    )

@app.get("/agendas", response_class=HTMLResponse)
def list_agendas(request: Request):
    # Assume markdown_texts_df has columns 'ds' and 'markdown_path'
    agendas = markdown_texts_df.copy()
    agendas['year'] = agendas['ds'].astype(str).str[:4]
    agendas_by_year = {}
    for year, group in agendas.groupby('year'):
        agendas_by_year[year] = group.sort_values('ds',ascending=False).to_dict(orient='records')
    return templates.TemplateResponse(
        "agendas.html",
        {
            "request": request,
            "agendas_by_year": dict(sorted(agendas_by_year.items(), reverse=True))
        }
    )

