from urllib.parse import urlparse


def url_is_valid(url: str) -> bool:
    """Return True if URL is a valid http/https URL."""
    try:
        result = urlparse(url)
        return result.scheme in ('http', 'https') and bool(result.netloc)
    except Exception:
        return False
