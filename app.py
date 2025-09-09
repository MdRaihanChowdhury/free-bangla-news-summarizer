import json
import feedparser
from flask import Flask, render_template, jsonify
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.text_rank import TextRankSummarizer
from flask_caching import Cache

app = Flask(__name__)
cache = Cache(app, config={"CACHE_TYPE": "simple", "CACHE_DEFAULT_TIMEOUT": 3600})

with open("feeds.json", "r", encoding="utf-8") as f:
    FEEDS = json.load(f)

def summarize_text(text, sentences_count=3):
    parser = PlaintextParser.from_string(text, Tokenizer("bangla"))
    summarizer = TextRankSummarizer()
    summary = summarizer(parser.document, sentences_count)
    return " ".join([str(s) for s in summary])

@app.route("/fetch")
def fetch_feeds():
    results = []
    for feed_url in FEEDS:
        d = feedparser.parse(feed_url)
        for entry in d.entries[:10]:
            link = entry.get("link")
            title = entry.get("title", "")
            if not link:
                continue
            content = ""
            if "content" in entry and len(entry.content) > 0:
                content = entry.content[0].value
            else:
                content = entry.get("summary", entry.get("description", ""))
            if not content.strip():
                continue
            summary = summarize_text(content)
            results.append({
                "title": title,
                "link": link,
                "summary": summary
            })
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
