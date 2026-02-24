"""
Generic job posting parser. Fallback for any site without a dedicated parser.
Uses common HTML patterns and heuristics.
"""
import re
from bs4 import BeautifulSoup


def parse_generic_posting(html: str) -> dict:
    """
    Parse a job posting using generic patterns.
    Returns a dict with whatever could be extracted — callers should handle None values.
    """
    soup = BeautifulSoup(html, 'lxml')

    return {
        'title': _extract_title(soup),
        'company': _extract_company(soup),
        'description': _extract_description(soup),
        'skills': _extract_skills(soup),
        'location': _extract_location(soup),
        'salary': _extract_salary(soup),
        'seniority': _extract_seniority(soup),
        'employment_type': _extract_employment_type(soup),
    }


def _extract_title(soup: BeautifulSoup) -> str | None:
    # Try JSON-LD structured data first (most reliable)
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            import json
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get('@type') == 'JobPosting':
                return data.get('title')
        except Exception:
            pass

    # Try common title patterns
    for selector in ['h1', '[class*="job-title"]', '[class*="jobTitle"]',
                     '[class*="position-title"]', '[id*="job-title"]']:
        el = soup.select_one(selector)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)

    # Fall back to page <title>
    if soup.title:
        title = soup.title.string or ''
        # Strip common suffixes like "| LinkedIn", "- Indeed"
        title = re.split(r'\s*[|\-–]\s*', title)[0].strip()
        if title:
            return title

    return None


def _extract_company(soup: BeautifulSoup) -> str | None:
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            import json
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get('@type') == 'JobPosting':
                hiring_org = data.get('hiringOrganization', {})
                if isinstance(hiring_org, dict):
                    return hiring_org.get('name')
        except Exception:
            pass

    for selector in ['[class*="company-name"]', '[class*="companyName"]',
                     '[class*="employer"]', '[class*="org-name"]']:
        el = soup.select_one(selector)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)

    return None


def _extract_description(soup: BeautifulSoup) -> str | None:
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            import json
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get('@type') == 'JobPosting':
                desc = data.get('description', '')
                if desc:
                    # Strip HTML tags from JSON-LD description
                    return BeautifulSoup(desc, 'lxml').get_text(separator=' ', strip=True)
        except Exception:
            pass

    for selector in ['[class*="job-description"]', '[class*="jobDescription"]',
                     '[class*="description"]', 'article', 'main']:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator=' ', strip=True)
            if len(text) > 200:  # Enough to be a real description
                return text

    return None


def _extract_skills(soup: BeautifulSoup) -> list[str]:
    """Extract skills by looking for known tech keywords in the description."""
    KNOWN_SKILLS = [
        'Python', 'TypeScript', 'JavaScript', 'Go', 'Rust', 'Java', 'C\\+\\+', 'C#',
        'SQL', 'PostgreSQL', 'MySQL', 'MongoDB', 'Redis',
        'Docker', 'Kubernetes', 'Terraform', 'Ansible', 'Helm',
        'AWS', 'GCP', 'Azure', 'Linux', 'Git', 'CI/CD',
        'Prometheus', 'Grafana', 'Elasticsearch', 'Kafka',
        'React', 'Node\\.js', 'FastAPI', 'Flask', 'Django',
        'Airflow', 'Spark', 'dbt',
    ]

    desc_el = soup.find(attrs={'class': re.compile(r'description', re.I)})
    text = desc_el.get_text() if desc_el else soup.get_text()

    found = []
    for skill in KNOWN_SKILLS:
        if re.search(r'\b' + skill + r'\b', text, re.IGNORECASE):
            # Use canonical capitalisation
            found.append(re.sub(r'\\', '', skill))

    return found


def _extract_location(soup: BeautifulSoup) -> str | None:
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            import json
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get('@type') == 'JobPosting':
                loc = data.get('jobLocation', {})
                if isinstance(loc, dict):
                    addr = loc.get('address', {})
                    if isinstance(addr, dict):
                        parts = [addr.get('addressLocality'), addr.get('addressCountry')]
                        return ', '.join(p for p in parts if p)
        except Exception:
            pass

    for selector in ['[class*="location"]', '[class*="job-location"]']:
        el = soup.select_one(selector)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)

    return None


def _extract_salary(soup: BeautifulSoup) -> str | None:
    text = soup.get_text()
    # Match patterns like €50k, €50,000, $80k-$100k, 50 000 € etc.
    match = re.search(
        r'[\$€£]\s*[\d,\.]+\s*[k]?\s*[-–]\s*[\$€£]?\s*[\d,\.]+\s*[k]?'
        r'|[\d\s]+\s*[€$£]\s*/\s*(year|month|yr|mo)',
        text, re.IGNORECASE
    )
    return match.group(0).strip() if match else None


def _extract_seniority(soup: BeautifulSoup) -> str | None:
    text = soup.get_text().lower()
    if any(w in text for w in ['senior', 'lead', 'staff', 'principal']):
        return 'Senior'
    if any(w in text for w in ['junior', 'entry', 'graduate', 'trainee']):
        return 'Junior'
    if 'mid' in text or 'intermediate' in text:
        return 'Mid'
    return None


def _extract_employment_type(soup: BeautifulSoup) -> str | None:
    text = soup.get_text().lower()
    if 'full-time' in text or 'full time' in text:
        return 'Full-time'
    if 'part-time' in text or 'part time' in text:
        return 'Part-time'
    if 'contract' in text or 'freelance' in text:
        return 'Contract'
    if 'internship' in text or 'trainee' in text or 'intern' in text:
        return 'Internship'
    return None
