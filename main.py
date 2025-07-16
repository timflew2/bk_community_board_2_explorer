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
postal_codes = (
    agenda_items_df.postal_code.apply(lambda x: str(int(x)) if isinstance(x, float) and x>0 else None)
)
agenda_items_df.drop("postal_code",axis=1,inplace=True)
agenda_items_df.loc[:,"postal_code"] = postal_codes

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
def explore(
    request: Request,
    agg: str = Query('application_type', description="Column to aggregate"),
    postal_code: str = Query(None, description="Postal code to filter"),
    application_type: str = Query(None, description="Application type to filter"),
    business_name: str = Query(None, description="Business name to filter"),
    business_address: str = Query(None, description="Business address to filter")
):
    # Only allow aggregations on certain columns
    allowed_aggs = ['application_type', 'business_name', 'business_address', 'postal_code']
    if agg not in allowed_aggs:
        agg = 'application_type'
    filtered_df = agenda_items_df
    if postal_code:
        filtered_df = filtered_df[filtered_df['postal_code'].astype(str).str.strip() == postal_code.strip()]
    if application_type:
        filtered_df = filtered_df[filtered_df['application_type'].astype(str).str.strip() == application_type.strip()]
    if business_name:
        filtered_df = filtered_df[filtered_df['business_name'].astype(str).str.strip() == business_name.strip()]
    if business_address:
        filtered_df = filtered_df[filtered_df['business_address'].astype(str).str.strip() == business_address.strip()]
    counts = filtered_df[agg].value_counts().sort_values(ascending=False)
    counts = counts.reset_index()
    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "agg": agg,
            "counts": counts.to_dict(orient='records'),
            "allowed_aggs": allowed_aggs,
            "postal_code": postal_code or "",
            "application_type": application_type or "",
            "business_name": business_name or "",
            "business_address": business_address or ""
        }
    )

@app.get("/map", response_class=HTMLResponse)
def explore_map(request: Request, 
                ds_start: str = Query(None, description="Start ds (inclusive)"),
                ds_end: str = Query(None, description="End ds (inclusive)"),
                application_type: list[str] = Query(None, description="Application types to filter")):
    # Drop rows with missing coordinates
    map_df = agenda_items_df.dropna(subset=["latitude", "longitude"])
    # Determine the most recent year in the ds column
    ds_years = map_df["ds"].astype(str).str[:4]
    most_recent_year = ds_years.max()
    # If ds_start and ds_end are not provided, default to the most recent year
    if ds_start is None and ds_end is None:
        year_mask = map_df["ds"].astype(str).str.startswith(most_recent_year)
        year_ds = map_df[year_mask]["ds"]
        if not year_ds.empty:
            ds_start = year_ds.min()
            ds_end = year_ds.max()
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
            info += f'<br><a href="{markdown_url}" target="_blank">View Markdown</a>'
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

@app.get("/latest", response_class=HTMLResponse)
def latest_agenda_items(request: Request):
    # Find the latest ds value
    latest_ds = agenda_items_df['ds'].max()
    latest_items = agenda_items_df[agenda_items_df['ds'] == latest_ds]
    latest_items_list = []
    for _, item in latest_items.iterrows():
        # Find historical items with same business_name OR business_address, but different ds
        historical = agenda_items_df[(
            ((agenda_items_df['business_name'] == item['business_name']) | (agenda_items_df['business_address'] == item['business_address'])) &
            (agenda_items_df['ds'] != item['ds'])
        )]
        # Add match_reason to each historical item
        historical_items = []
        for _, hist in historical.iterrows():
            hist_dict = hist.to_dict()
            if hist['business_name'] == item['business_name'] and hist['business_address'] == item['business_address']:
                hist_dict['match_reason'] = 'business_name & business_address'
            elif hist['business_name'] == item['business_name']:
                hist_dict['match_reason'] = 'business_name'
            elif hist['business_address'] == item['business_address']:
                hist_dict['match_reason'] = 'business_address'
            else:
                hist_dict['match_reason'] = ''
            historical_items.append(hist_dict)
        item_dict = item.to_dict()
        item_dict['historical_items'] = historical_items
        item_dict['has_history'] = len(historical_items) > 0
        latest_items_list.append(item_dict)
    # Sort so items with history appear first
    latest_items_list.sort(key=lambda x: not x['has_history'])
    return templates.TemplateResponse(
        "latest.html",
        {
            "request": request,
            "latest_items": latest_items_list,
            "latest_ds": latest_ds
        }
    )

