# UI screenshots

Streamlit UI captures at 1440×900 (viewport). Regenerate after UI changes:

```powershell
uv run streamlit run streamlit_app.py
uv run python scripts/capture_screenshots.py
```

Requires the app on `http://localhost:8501`. `chat-response.png` submits a live comparison question and needs `GROQ_API_KEY`.

| Page | File |
|------|------|
| Chat (empty) | [chat.png](chat.png) |
| Chat (agent response) | [chat-response.png](chat-response.png) |
| Crawled catalog | [catalog.png](catalog.png) |
| Context, tools, and usage | [usage.png](usage.png) |
| About | [about.png](about.png) |

## Previews

### Chat

![Chat empty state](chat.png)

### Comparison response

![Chat with agent comparison](chat-response.png)

### Crawled catalog

![Crawled catalog browser](catalog.png)

### Context, tools, and usage

![Token and tool usage](usage.png)

### About

![About page](about.png)
