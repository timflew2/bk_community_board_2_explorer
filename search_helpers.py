import html
import markdown2
import re

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