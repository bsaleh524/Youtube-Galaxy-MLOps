import re
from pathlib import Path

from pipeline.publish import home_files

ROOT = Path(__file__).resolve().parents[1]
HTACCESS = ROOT / "web" / "public" / ".htaccess"
HOME = ROOT / "web" / "home"


def test_htaccess_cache_rules():
    text = HTACCESS.read_text(encoding="utf-8")
    long_rule = re.search(r'<FilesMatch "[^"]*js[^"]*css[^"]*json[^"]*">[^<]*max-age=31536000, immutable', text)
    assert long_rule, "versioned js/css/json must be cached for a year"
    no_cache = re.search(r'<FilesMatch "\^\(index\\\.html\|manifest\\\.json\)\$">[^<]*no-cache', text)
    assert no_cache, "index.html and manifest.json must never be cached"
    # mod_headers applies sections in order, so the no-cache section has to come after the long one
    assert no_cache.start() > long_rule.start()
    deflate = re.search(r"AddOutputFilterByType DEFLATE ([^\n]+)", text)
    assert deflate
    for t in ("application/json", "text/javascript", "text/css", "text/html"):
        assert t in deflate.group(1)


def test_home_links_galaxy():
    html = (HOME / "index.html").read_text(encoding="utf-8")
    assert 'href="/galaxy/"' in html
    assert 'href="home.css"' in html
    assert 'name="viewport"' in html
    assert "<script" not in html


def test_home_plan_has_no_htaccess_or_dirs():
    paths = [p for p, _ in home_files(HOME)]
    assert paths and all("/" not in p for p in paths)
    assert ".htaccess" not in paths
