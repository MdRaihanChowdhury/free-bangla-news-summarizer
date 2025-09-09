import json
import feedparser
from flask import Flask, render_template, jsonify
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.text_rank import TextRankSummarizer
from flask_caching import Cache

app = Flask(__name__)
cache = Cache(app, config={"CACHE_TYPE": "simple", "CACHE_DEFAULT_TIMEOUT": 3600})

# Tested Bangla feeds
FEEDS = [
    "https://www.prothomalo.com/rss",
    "https://bangla.bdnews24.com/rss",
    "https://www.jagonews24.com/feed",
    "https://www.bbc.com/bengali/index.xml"
]

def summarize_text(text, sentences_count=3):
    try:
        parser = PlaintextParser.from_string(text, Tokenizer("bangla"))
        summarizer = TextRankSummarizer()
        summary = summarizer(parser.document, sentences_count)
        return " ".join([str(s) for s in summary])
    except Exception:
        # fallback: return first 200 chars if summarizer fails
        return text[:200]

@app.route("/fetch")
def fetch_feeds():
    results = []
    for feed_url in FEEDS:
        try:
            d = feedparser.parse(feed_url)
            for entry in d.entries[:10]:
                link = entry.get("link")
                title = entry.get("title","")
                if not link:
                    continue
                content = ""
                if "content" in entry and len(entry.content) > 0:
                    content = entry.content[0].value
                else:
                    content = entry.get("summary","") or entry.get("description","")
                if not content.strip():
                    continue
                summary = summarize_text(content)
                results.append({
                    "title": title,
                    "link": link,
                    "summary": summary
                })
        except Exception as e:
            print("Feed error:", feed_url, e)
            continue
    cache.set("latest_articles", results, timeout=3600)
    return jsonify({"added": len(results)})

@app.route("/api/latest")
def api_latest():
    articles = cache.get("latest_articles") or []
    return jsonify(articles)

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
