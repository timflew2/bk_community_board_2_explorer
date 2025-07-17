import html
import markdown2
import re
import faiss
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

sentence_transformer = SentenceTransformer("all-MiniLM-L6-v2")
faiss_markdown_snippets_index = faiss.read_index("data/faiss_sentence_transformer_markdown_snippets.index")
distance_thresh = 1.5

def search_markdown_dataframe(markdown_texts_df, query):
    matches = markdown_texts_df[markdown_texts_df['markdown_text'].str.contains(query, case=False, na=False)]
    matches = matches.sort_values("ds", ascending=False)
    results = []
    for _, row in matches.iterrows():
        ds = row['ds']
        text_lines = row['markdown_text'].splitlines()
        text_lower_lines = [line.lower() for line in text_lines]
        snippets = []
        for i, line in enumerate(text_lower_lines):
            start_idx = 0
            while True:
                idx = line.find(query.lower(), start_idx)
                if idx == -1:
                    break
                snippet_start = max(0, i - 2)
                snippet_end = min(len(text_lines), i + 3)
                snippet_lines = text_lines[snippet_start:snippet_end]
                snippet_md = []
                for snippet_line in snippet_lines:
                    snippet_line_hl = snippet_line
                    idx_hl = snippet_line.lower().find(query.lower())
                    while idx_hl != -1:
                        snippet_line_hl = (
                            snippet_line_hl[:idx_hl]
                            + '<mark><b>' + snippet_line_hl[idx_hl:idx_hl+len(query)] + '</b></mark>'
                            + snippet_line_hl[idx_hl+len(query):]
                        )
                        idx_hl = snippet_line_hl.lower().find(query.lower(), idx_hl + len('<mark><b>') + len(query) + len('</b></mark>'))
                    snippet_md.append(snippet_line_hl)
                snippet = '\n'.join(snippet_md)
                snippet_html = markdown2.markdown(snippet)
                snippet_html = snippet_html.replace('&lt;mark&gt;', '<mark>').replace('&lt;/mark&gt;', '</mark>')
                snippet_html = snippet_html.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')
                snippet_html = re.sub(r'<a ', '<a target="_blank" rel="noopener noreferrer" ', snippet_html)
                snippets.append(snippet_html)
                start_idx = idx + len(query)
        if snippets:
            results.append({
                "ds": html.escape(str(ds)),
                "snippets": snippets,
                "full_id": html.escape(str(ds)),
            })
    return results

def search_markdown_snippets_dataframe_embedding(markdown_snippets_df: pd.DataFrame, query: str, k: int = 100):
    """
    Search the markdown_snippets_df using semantic similarity with SentenceTransformer and FAISS.
    Returns the top k most similar rows, with those containing the query in the snippet sorted to the top, highlighted in bold orange, and with Markdown links rendered as HTML <a> tags in the preview.
    """
    def markdown_links_to_html(text):
        # Replace markdown links [text](url) with HTML <a> tags
        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank">\1</a>', text)

    query_embedding = sentence_transformer.encode([query], convert_to_numpy=True)
    distances, indices = faiss_markdown_snippets_index.search(query_embedding, k)
    results = []
    for idx, distance in zip(indices[0], distances[0]):
        
        if idx < len(markdown_snippets_df):
            row = markdown_snippets_df.iloc[idx]
            snippet = row.get("markdown_snippet", "")
            snippet_lower = snippet.lower()
            query_lower = query.lower()
            contains_query = query_lower in snippet_lower

            # Exclude if not similar
            if distance > distance_thresh and not contains_query:
                continue

            # Highlight the query in the snippet preview if present
            if contains_query:
                def highlight_query(m):
                    return f'<span style="color: orange"><b>{m.group(0)}</b></span>'
                snippet_highlighted = re.sub(re.escape(query), highlight_query, snippet, flags=re.IGNORECASE)
            else:
                snippet_highlighted = snippet
            # Convert markdown links to HTML <a> tags
            snippet_html = markdown_links_to_html(snippet_highlighted)
            results.append({
                "ds": html.escape(str(row["ds"])),
                "distance": float(distance),
                "full_id": html.escape(str(row["ds"])),
                "snippet": snippet_html,
                "markdown_path": row.get("markdown_path", ""),
                "contains_query": contains_query,
                "snippet_type": row.get("snippet_type", "")
            })
    # Sort: those with query in snippet first, then by distance
    results.sort(key=lambda x: (not x["contains_query"], x["distance"]))

    # Only keep the top (best) result per unique markdown_path
    seen_paths = set()
    unique_results = []
    for result in results:
        path = result.get("markdown_path", None)
        if path and path not in seen_paths:
            unique_results.append(result)
            seen_paths.add(path)
    return unique_results 