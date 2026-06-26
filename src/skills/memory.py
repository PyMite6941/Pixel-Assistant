"""
Lightweight RAG memory for Pixel Assistant.
Stores facts and retrieves relevant ones via keyword + TF-IDF scoring.
No external dependencies required.
"""
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

MEMORY_FILE = Path(__file__).parent.parent / "functionalities" / "memory_rag.json"


def _load():
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(memories):
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(memories, indent=2, ensure_ascii=False), encoding="utf-8")


def remember(fact: str, source: str = "user") -> str:
    """Store a fact with timestamp and source."""
    memories = _load()
    existing = [m for m in memories if _similarity(m["fact"], fact) > 0.85]
    if existing:
        existing[0]["fact"] = fact
        existing[0]["updated"] = datetime.now().isoformat()
        _save(memories)
        return f"Updated existing memory: {fact[:80]}"
    memories.append({
        "id": len(memories) + 1,
        "fact": fact,
        "source": source,
        "created": datetime.now().isoformat(),
        "keywords": _extract_keywords(fact),
    })
    _save(memories)
    return f"Remembered: {fact[:80]}"


def recall(query: str, top_k: int = 5) -> list[dict]:
    """Find most relevant memories for a query using keyword + TF-IDF scoring."""
    memories = _load()
    if not memories:
        return []
    query_keywords = set(_extract_keywords(query))
    total = len(memories)
    for m in memories:
        matching = query_keywords & set(m["keywords"])
        if not matching:
            m["score"] = 0
            continue
        tf = sum(1 for kw in m["keywords"] if kw in matching) / max(len(m["keywords"]), 1)
        idf = sum(math.log((total + 1) / (1 + sum(1 for o in memories if kw in o["keywords"]))) for kw in matching)
        m["score"] = tf * idf
    memories.sort(key=lambda x: x["score"], reverse=True)
    return [m for m in memories if m["score"] > 0][:top_k]


def forget(keyword: str) -> int:
    """Remove memories matching keyword. Returns count removed."""
    memories = _load()
    before = len(memories)
    memories = [m for m in memories if keyword.lower() not in m["fact"].lower()]
    _save(memories)
    return before - len(memories)


def all_memories() -> list[dict]:
    """Return all memories."""
    return _load()


def clear():
    """Delete all memories."""
    _save([])


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from text."""
    text = text.lower()
    stops = {"a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
             "have", "has", "had", "do", "does", "did", "will", "would", "could",
             "should", "may", "might", "shall", "can", "need", "dare", "ought",
             "used", "i", "you", "he", "she", "it", "we", "they", "me", "him",
             "her", "us", "them", "my", "your", "his", "its", "our", "their",
             "mine", "yours", "hers", "ours", "theirs", "this", "that", "these",
             "those", "some", "any", "no", "none", "many", "much", "few", "several",
             "all", "both", "each", "every", "other", "another", "such", "what",
             "which", "who", "whom", "whose", "when", "where", "why", "how",
             "and", "but", "or", "nor", "not", "so", "yet", "for", "with",
             "about", "against", "between", "into", "through", "during", "before",
             "after", "above", "below", "from", "to", "up", "down", "in", "out",
             "on", "off", "over", "under", "again", "further", "then", "once",
             "here", "there", "too", "very", "just", "also", "more", "less", "most",
             "least", "only", "enough", "own", "same", "than", "as"}
    words = re.findall(r"[a-z]+", text)
    keywords = []
    for w in words:
        if w not in stops and len(w) > 2:
            keywords.append(w)
            if len(w) >= 4:
                for i in range(len(w) - 2):
                    keywords.append(w[i:i+3])
    return list(set(keywords))


def _similarity(a: str, b: str) -> float:
    """Simple character-level similarity (Dice coefficient on bigrams)."""
    a_bigrams = set(a[i:i+2] for i in range(len(a)-1))
    b_bigrams = set(b[i:i+2] for i in range(len(b)-1))
    if not a_bigrams or not b_bigrams:
        return 0.0
    intersection = a_bigrams & b_bigrams
    return 2.0 * len(intersection) / (len(a_bigrams) + len(b_bigrams))
