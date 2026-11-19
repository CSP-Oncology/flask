""" Sesh news model (same pattern as the Poway Recovery Center schedule, model/schedule.py there)

News is not typed in by hand: sync_news() pulls the stories from Sesh's own News page
(oncologysesh.com/news) and upserts them here, so this site's news changes when Sesh posts.
That site is a single-page app: its stories are a list of objects inside the app's JavaScript
({id, title, excerpt, content, date, author, category, image}), which is read from there.
If Sesh's site can't be reached, the last synced news stays.
"""
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from sqlalchemy import inspect, text

from __init__ import app, db


MONTHS = {m: i for i, m in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
     'September', 'October', 'November', 'December'], start=1)}


class NewsArticle(db.Model):
    """
    NewsArticle Model: one story from Sesh's News page.

    Attributes:
        id (Column): Primary key.
        _source_id (Column): The story's id on Sesh's site, used to upsert on each sync.
        _title, _excerpt, _content, _category, _author (Column): Copied from Sesh's site.
        _date (Column): The date as Sesh shows it ("June 4, 2026", or just "June 2026").
        _sort_date (Column): "YYYY-MM-DD" (or "YYYY-MM") for ordering and <time datetime>.
        _position (Column): Its place in Sesh's list; 0 is the featured story.
        _image_url (Column): The story's picture on Sesh's site.
        _url (Column): The story on Sesh's site: its own page if it has one, else Sesh's News page.
        _active (Column): False once the story disappears from Sesh's site.
        updated_at (Column): Last sync that touched this story.
    """
    __tablename__ = 'news_articles'

    id = db.Column(db.Integer, primary_key=True)
    _source_id = db.Column(db.String(64), unique=True, nullable=False)
    _title = db.Column(db.String(255), nullable=False)
    _excerpt = db.Column(db.Text, nullable=True)
    _content = db.Column(db.Text, nullable=True)
    _category = db.Column(db.String(64), nullable=True)
    _author = db.Column(db.String(128), nullable=True)
    _date = db.Column(db.String(64), nullable=True)
    _sort_date = db.Column(db.String(10), nullable=True)
    _position = db.Column(db.Integer, default=0, nullable=False)
    _image_url = db.Column(db.String(512), nullable=True)
    _url = db.Column(db.String(512), nullable=True)
    _active = db.Column(db.Boolean, default=True, nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def read(self):
        return {
            "id": self.id,
            "title": self._title,
            "excerpt": self._excerpt or "",
            "content": self._content or "",
            "category": self._category or "News",
            "author": self._author or "",
            "date": self._date or "",
            "datetime": self._sort_date or "",
            "featured": self._position == 0,
            "image_url": self._image_url or "",
            "url": self._url or app.config['NEWS_SOURCE_URL'],
        }


def sort_date(text):
    """ "June 4, 2026" -> "2026-06-04"; "June 2026" -> "2026-06"; else "" """
    match = re.match(r'\s*([A-Za-z]+)\s+(?:(\d{1,2}),\s*)?(\d{4})', text or '')
    if not match or match.group(1).capitalize() not in MONTHS:
        return ''
    month = MONTHS[match.group(1).capitalize()]
    if match.group(2):
        return f"{match.group(3)}-{month:02d}-{int(match.group(2)):02d}"
    return f"{match.group(3)}-{month:02d}"


# ---- Sync from Sesh's News page ----

_sync_lock = threading.Lock()
sync_status = {"last_synced": None, "last_attempt": 0.0, "error": None, "count": 0}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "OncologySeshAPI/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode('utf-8', errors='replace')


def _flat_objects(source):
    """
    Every flat {key:"text", key:number, ...} object literal in a JavaScript bundle, as dicts.
    Strings are JSON-style (double quotes, backslash escapes), so each is decoded with json.loads.
    """
    pair = re.compile(r'\s*([A-Za-z_$][\w$]*)\s*:\s*("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?)\s*([,}])')
    found = []
    for start in re.finditer(r'\{(?=\s*[A-Za-z_$][\w$]*\s*:)', source):
        obj, pos = {}, start.end()
        while True:
            match = pair.match(source, pos)
            if not match:
                obj = None
                break
            value = match.group(2)
            obj[match.group(1)] = json.loads(value) if value.startswith('"') else float(value)
            pos = match.end()
            if match.group(3) == '}':
                break
        if obj:
            found.append(obj)
    return found


def fetch_sesh_news():
    """ The stories on Sesh's News page, in the order Sesh lists them (the first is featured) """
    site = app.config['NEWS_SITE_URL']
    page = _get(f'{site}/news')
    scripts = re.findall(r'<script[^>]+src="([^"]+\.js)"', page)
    if not scripts:
        raise ValueError("no app script on Sesh's News page")
    stories, seen = [], set()
    for script in scripts:
        source = _get(urllib.parse.urljoin(site + '/', script))
        # Stories with their own page are routes like path:"/news/evonexus-announcement"
        pages = re.findall(r'path\s*:\s*"(/news/[\w-]+)"', source)
        for obj in _flat_objects(source):
            if not {'id', 'title', 'excerpt', 'date'} <= obj.keys():
                continue
            key = str(int(obj['id'])) if isinstance(obj['id'], float) else str(obj['id'])
            if key in seen:
                continue
            seen.add(key)
            image = (obj.get('image') or '').strip()
            if image.startswith('data:'):
                image = ''  # pictures embedded in Sesh's code are too large to keep; the story shows without one
            elif image and not image.startswith(('http://', 'https://')):
                image = urllib.parse.urljoin(site + '/', urllib.parse.quote(image, safe='/'))
            title = obj['title'].lower()
            page = next((p for p in pages if p.rsplit('/', 1)[1].split('-')[0] in title), None)
            stories.append({
                'id': key,
                'url': f'{site}{page}' if page else app.config['NEWS_SOURCE_URL'],
                'title': obj['title'].strip(),
                'excerpt': obj.get('excerpt', '').strip(),
                'content': obj.get('content', '').strip(),
                'category': obj.get('category', 'News').strip(),
                'author': obj.get('author', '').strip(),
                'date': obj.get('date', '').strip(),
                'image_url': image,
            })
    if not stories:
        raise ValueError("no stories found on Sesh's News page")
    return stories


def sync_news():
    """
    Pull Sesh's news and upsert it. Stories no longer listed are marked inactive.
    If Sesh's site can't be reached, the last synced news stays. Returns sync_status.
    """
    with _sync_lock, app.app_context():
        sync_status["last_attempt"] = time.time()
        try:
            stories = fetch_sesh_news()
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError) as error:
            sync_status["error"] = f"Could not reach Sesh's News page: {error}"
            app.logger.error(sync_status["error"])
            return sync_status

        seen = set()
        for position, story in enumerate(stories):
            seen.add(story['id'])
            article = NewsArticle.query.filter_by(_source_id=story['id']).first()
            if article is None:
                article = NewsArticle(_source_id=story['id'])
                db.session.add(article)
            article._title = story['title'][:255]
            article._excerpt = story['excerpt']
            article._content = story['content']
            article._category = story['category'][:64]
            article._author = story['author'][:128]
            article._date = story['date'][:64]
            article._sort_date = sort_date(story['date'])
            article._position = position
            article._image_url = story['image_url'][:512]
            article._url = story['url'][:512]
            article._active = True
            article.updated_at = datetime.now(timezone.utc)
        for article in NewsArticle.query.filter(NewsArticle._active.is_(True)).all():
            if article._source_id not in seen:
                article._active = False
        db.session.commit()

        sync_status.update(last_synced=datetime.now(timezone.utc).isoformat(), error=None, count=len(stories))
        return sync_status


def sync_if_stale():
    """ Re-sync when the last attempt is older than NEWS_REFRESH_SECONDS (called on news reads) """
    if time.time() - sync_status["last_attempt"] >= app.config['NEWS_REFRESH_SECONDS'] and not _sync_lock.locked():
        sync_news()


def initNews():
    """ Create the news table and load Sesh's current news """
    with app.app_context():
        db.create_all()
        # News tables made before stories linked to their own page
        if '_url' not in [c['name'] for c in inspect(db.engine).get_columns('news_articles')]:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE news_articles ADD COLUMN _url VARCHAR(512)'))
    sync_news()
