import re
import xml.etree.ElementTree as ET
from typing import List, Any

from models.paper import Paper, Author


ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _extract_arxiv_id(entry: ET.Element) -> str | None:
    id_el = entry.find("atom:id", ARXIV_NS)
    if id_el is not None and id_el.text:
        m = re.search(r"abs/([^\s]+)", id_el.text)
        if m:
            return m.group(1)
    arxiv_id_el = entry.find("arxiv:id", ARXIV_NS)
    if arxiv_id_el is not None and arxiv_id_el.text:
        return arxiv_id_el.text.strip()
    return None


def _extract_year(entry: ET.Element) -> int | None:
    published = entry.find("atom:published", ARXIV_NS)
    if published is not None and published.text:
        m = re.match(r"(\d{4})", published.text)
        if m:
            return int(m.group(1))
    return None


def _extract_authors(entry: ET.Element) -> List[Author]:
    authors: List[Author] = []
    for author_el in entry.findall("atom:author", ARXIV_NS):
        name_el = author_el.find("atom:name", ARXIV_NS)
        name = name_el.text.strip() if name_el is not None and name_el.text else ""
        affiliation_el = author_el.find("arxiv:affiliation", ARXIV_NS)
        affiliation = affiliation_el.text.strip() if affiliation_el is not None and affiliation_el.text else None
        if name:
            authors.append(Author(name=name, affiliation=affiliation))
    return authors


def _extract_doi(entry: ET.Element) -> str | None:
    doi_el = entry.find("arxiv:doi", ARXIV_NS)
    if doi_el is not None and doi_el.text:
        return doi_el.text.strip()
    for link in entry.findall("atom:link", ARXIV_NS):
        title = link.get("title", "")
        href = link.get("href", "")
        if "doi" in title.lower() or "doi.org" in href:
            m = re.search(r"10\.\d{4,}/[^\s]+", href)
            if m:
                return m.group(0)
    return None


def _extract_abstract(entry: ET.Element) -> str:
    summary = entry.find("atom:summary", ARXIV_NS)
    if summary is not None and summary.text:
        return summary.text.strip()
    return ""


def parse_arxiv_response(raw_content: str) -> List[Paper]:
    papers: List[Paper] = []
    try:
        root = ET.fromstring(raw_content)
    except ET.ParseError:
        return papers
    for entry in root.findall("atom:entry", ARXIV_NS):
        title_el = entry.find("atom:title", ARXIV_NS)
        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        if not title:
            continue
        url = ""
        id_link = entry.find("atom:id", ARXIV_NS)
        if id_link is not None and id_link.text:
            url = id_link.text.strip()
        arxiv_id = _extract_arxiv_id(entry)
        doi = _extract_doi(entry)
        paper = Paper(
            title=title,
            authors=_extract_authors(entry),
            abstract=_extract_abstract(entry),
            year=_extract_year(entry),
            venue=None,
            doi=doi,
            arxiv_id=arxiv_id,
            url=url or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else url),
            citation_count=0,
            references_count=0,
            source=["arxiv"],
            raw={"xml": raw_content[:500]},
        )
        papers.append(paper)
    return papers
