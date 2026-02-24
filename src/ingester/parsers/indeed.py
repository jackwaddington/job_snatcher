"""
Indeed job posting parser.
Selectors current as of early 2026 — may need updating if Indeed changes their HTML.
Falls back to generic parser if key elements are not found.
"""
from bs4 import BeautifulSoup
from src.ingester.parsers.generic import parse_generic_posting


def parse_indeed_posting(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')

    title = (
        _text(soup, 'h1.jobTitle') or
        _text(soup, '[class*="jobTitle"]') or
        _text(soup, 'h1')
    )

    company = (
        _text(soup, '[data-company-name]') or
        _text(soup, '.companyName') or
        _text(soup, '[class*="companyName"]')
    )

    description_el = (
        soup.select_one('#jobDescriptionText') or
        soup.select_one('[class*="jobDescriptionText"]')
    )
    description = description_el.get_text(separator=' ', strip=True) if description_el else None

    location = (
        _text(soup, '[data-testid="job-location"]') or
        _text(soup, '.companyLocation') or
        _text(soup, '[class*="companyLocation"]')
    )

    # If we couldn't get the key fields, fall back to generic
    if not title or not description:
        result = parse_generic_posting(html)
        result['title'] = result['title'] or title
        result['company'] = result['company'] or company
        result['location'] = result['location'] or location
        return result

    from src.ingester.parsers.generic import (
        _extract_skills, _extract_salary,
        _extract_seniority, _extract_employment_type,
    )

    return {
        'title': title,
        'company': company,
        'description': description,
        'location': location,
        'skills': _extract_skills(soup),
        'salary': _extract_salary(soup),
        'seniority': _extract_seniority(soup),
        'employment_type': _extract_employment_type(soup),
    }


def _text(soup: BeautifulSoup, selector: str) -> str | None:
    el = soup.select_one(selector)
    return el.get_text(strip=True) if el else None
