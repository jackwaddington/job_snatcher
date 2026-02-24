"""
LinkedIn job posting parser.

NOTE: LinkedIn is JavaScript-heavy. Fetching with requests returns limited content.
This parser handles both:
  - Static HTML (may only get partial data)
  - Selenium-rendered HTML (full content, future enhancement)

Falls back to generic parser if key elements are not found.
"""
from bs4 import BeautifulSoup
from src.ingester.parsers.generic import parse_generic_posting


def parse_linkedin_posting(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')

    title = (
        _text(soup, 'h1.top-card-layout__title') or
        _text(soup, 'h1.t-24') or
        _text(soup, '.job-details-jobs-unified-top-card__job-title') or
        _text(soup, 'h1')
    )

    company = (
        _text(soup, '.topcard__org-name-link') or
        _text(soup, '.top-card-layout__company-name') or
        _text(soup, '.job-details-jobs-unified-top-card__company-name')
    )

    description_el = (
        soup.select_one('.show-more-less-html__markup') or
        soup.select_one('[class*="description__text"]') or
        soup.select_one('.jobs-description-content__text')
    )
    description = description_el.get_text(separator=' ', strip=True) if description_el else None

    location = (
        _text(soup, '.topcard__flavor--bullet') or
        _text(soup, '.job-details-jobs-unified-top-card__bullet') or
        _text(soup, '[class*="job-location"]')
    )

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
