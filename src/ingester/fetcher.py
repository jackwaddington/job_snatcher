import requests
from urllib.parse import urlparse

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}


def detect_job_source(url: str) -> str:
    """Detect which job board the URL is from."""
    domain = urlparse(url).netloc.lower()
    if 'linkedin.com' in domain:
        return 'linkedin'
    if 'indeed.com' in domain:
        return 'indeed'
    if 'duunitori.fi' in domain:
        return 'duunitori'
    return 'generic'


def fetch_html(url: str, timeout: int = 30) -> str:
    """
    Fetch HTML from a URL using requests.

    For JavaScript-heavy sites (LinkedIn) this may return incomplete HTML.
    Selenium support can be added later if needed.
    """
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text
