import urllib.parse
import requests
from bs4 import BeautifulSoup

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


class Search:
    def __init__(self, query: str):
        self.query = query

    def search(self, max_results: int = 5) -> str:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(self.query)}"
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for r in soup.select(".result__body")[:max_results]:
                title = r.select_one(".result__title")
                snippet = r.select_one(".result__snippet")
                if title and snippet:
                    results.append(f"• {title.get_text(strip=True)}: {snippet.get_text(strip=True)}")
            return "\n".join(results) if results else "No results found."
        except Exception as e:
            return f"Search error: {e}"
