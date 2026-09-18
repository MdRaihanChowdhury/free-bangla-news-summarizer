import json
import hashlib
import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urlparse
import feedparser
from flask import Flask, render_template, jsonify, request, Response
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.text_rank import TextRankSummarizer
from flask_caching import Cache

app = Flask(__name__)
cache = Cache(app, config={"CACHE_TYPE": "simple", "CACHE_DEFAULT_TIMEOUT": 3600})
SITE_DESCRIPTION = "বাংলাদেশের বিশ্বস্ত সংবাদমাধ্যম থেকে বাংলা খবরের স্বয়ংক্রিয় সংক্ষিপ্তসার, সর্বশেষ আপডেট ও বিভাগভিত্তিক সংবাদ।"

DEFAULT_FEEDS = [
    "https://www.prothomalo.com/rss",
    "https://bangla.bdnews24.com/rss",
    "https://www.jagonews24.com/feed",
    "https://www.bbc.com/bengali/index.xml"
]

try:
    with open("feeds.json", encoding="utf-8") as feeds_file:
        FEEDS = json.load(feeds_file)
except (FileNotFoundError, json.JSONDecodeError):
    FEEDS = DEFAULT_FEEDS

def summarize_text(text, sentences_count=3):
    try:
        parser = PlaintextParser.from_string(text, Tokenizer("bangla"))
        summarizer = TextRankSummarizer()
        summary = summarizer(parser.document, sentences_count)
        return " ".join([str(s) for s in summary])
    except Exception:
        # fallback: return first 200 chars if summarizer fails
        return text[:200]

def clean_feed_text(value):
    text = unescape(value or "")
    text = re.sub(r"<script[^>]*>.*?</script>|<style[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()

def get_published_at(entry):
    published = entry.get("published_parsed") or entry.get("updated_parsed")
    if not published:
        return ""
    return datetime(*published[:6], tzinfo=timezone.utc).isoformat()

def article_slug(title, link):
    words = re.findall(r"[a-z0-9]+", title.lower())
    readable = "-".join(words[:8]) or "news"
    suffix = hashlib.sha1(link.encode("utf-8")).hexdigest()[:8]
    return f"{readable}-{suffix}"

def extract_thumbnail(entry):
    media = entry.get("media_content") or entry.get("media_thumbnail") or []
    if media and isinstance(media, list):
        image_url = media[0].get("url")
        if image_url:
            return image_url
    enclosures = entry.get("enclosures") or []
    for enclosure in enclosures:
        if enclosure.get("type", "").startswith("image/") and enclosure.get("href"):
            return enclosure["href"]
    content = unescape(entry.get("summary", "") or entry.get("description", ""))
    image_match = re.search(r'<img[^>]+src=["\']([^"\']+)', content, re.IGNORECASE)
    if image_match:
        return image_match.group(1)
    srcset_match = re.search(r'(?:srcset|data-srcset)=["\']([^"\']+)', content, re.IGNORECASE)
    if srcset_match:
        return srcset_match.group(1).split(",")[0].strip().split(" ")[0]
    return ""

def classify_article(entry, text):
    article_text = f"{entry.get('title', '')} {text}".lower()
    tags = " ".join(tag.get("term", "") for tag in (entry.get("tags") or [])).lower()
    topic_text = f"{article_text} {tags}"
    categories = {
        "আন্তর্জাতিক": ["আন্তর্জাতিক", "বিশ্ব", "যুক্তরাষ্ট্র", "ভারত", "পাকিস্তান", "ইউক্রেন", "রাশিয়া", "ইরান", "চীন", "সৌদি", "ট্রাম্প"],
        "অর্থনীতি": ["অর্থনীতি", "অর্থ", "বাজেট", "ব্যাংক", "শেয়ার", "বাজার", "দাম", "টাকা", "ডলার", "ব্যবসা", "জ্বালানি"],
        "প্রযুক্তি": ["প্রযুক্তি", "প্রযুক্তি", "এআই", "এআই", "সফটওয়্যার", "মোবাইল", "ইন্টারনেট", "কম্পিউটার", "সাইবার"],
        "খেলা": ["খেলা", "ক্রিকেট", "ফুটবল", "ম্যাচ", "রান", "উইকেট", "গোল", "বিশ্বকাপ"],
        "জাতীয়": ["বাংলাদেশ", "ঢাকা", "সরকার", "নির্বাচন", "সংসদ", "আদালত", "পুলিশ", "রাজনীতি", "শিক্ষা", "স্বাস্থ্য"]
    }
    for category, keywords in categories.items():
        if any(keyword in topic_text for keyword in keywords):
            return category
    return "জাতীয়"

@app.route("/fetch")
def fetch_feeds():
    results = []
    for feed_url in FEEDS:
        try:
            d = feedparser.parse(feed_url)
            for entry in d.entries[:10]:
                link = entry.get("link")
                title = clean_feed_text(entry.get("title", ""))
                if not link:
                    continue
                content = ""
                if "content" in entry and len(entry.content) > 0:
                    content = entry.content[0].value
                else:
                    content = entry.get("summary","") or entry.get("description","")
                clean_content = clean_feed_text(content)
                if not clean_content:
                    continue
                summary = summarize_text(clean_content)
                results.append({
                    "title": title,
                    "slug": article_slug(title, link),
                    "link": link,
                    "summary": summary,
                    "thumbnail": extract_thumbnail(entry),
                    "source": urlparse(feed_url).netloc.replace("www.", ""),
                    "category": classify_article(entry, clean_content),
                    "published_at": get_published_at(entry)
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

@app.route("/news/<slug>")
def article_page(slug):
    articles = cache.get("latest_articles") or []
    article = next((item for item in articles if item.get("slug") == slug), None)
    if not article:
        return render_template("404.html"), 404
    return render_template(
        "article.html",
        article=article,
        site_url=request.url_root.rstrip("/")
    )

@app.route("/")
def index():
    return render_template(
        "index.html",
        site_url=request.url_root.rstrip("/"),
        site_description=SITE_DESCRIPTION
    )

@app.route("/robots.txt")
def robots():
    site_url = request.url_root.rstrip("/")
    body = f"User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /fetch\nSitemap: {site_url}/sitemap.xml\n"
    return Response(body, mimetype="text/plain")

@app.route("/sitemap.xml")
def sitemap():
    site_url = request.url_root.rstrip("/")
    articles = cache.get("latest_articles") or []
    article_urls = "\n".join(
        f"  <url><loc>{site_url}/news/{article['slug']}</loc><changefreq>daily</changefreq><priority>0.8</priority></url>"
        for article in articles if article.get("slug")
    )
    body = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{site_url}/</loc>
    <changefreq>hourly</changefreq>
    <priority>1.0</priority>
  </url>
{article_urls}
</urlset>'''
    return Response(body, mimetype="application/xml")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
