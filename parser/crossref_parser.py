from typing import List, Dict, Any

from models.paper import Paper, Author


def _extract_year(item: Dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        pub = item.get(key)
        if pub and "date-parts" in pub and pub["date-parts"]:
            parts = pub["date-parts"][0]
            if parts and isinstance(parts[0], int):
                return parts[0]
    return None


def _extract_authors(item: Dict[str, Any]) -> List[Author]:
    authors: List[Author] = []
    for a in item.get("author", []) or []:
        given = a.get("given", "") or ""
        family = a.get("family", "") or ""
        name = " ".join(part for part in [given, family] if part).strip()
        if not name:
            name = a.get("name", "") or ""
        affiliation = None
        affs = a.get("affiliation", []) or []
        if affs and isinstance(affs, list):
            first = affs[0]
            if isinstance(first, dict):
                affiliation = first.get("name")
            elif isinstance(first, str):
                affiliation = first
        orcid = a.get("ORCID")
        if orcid:
            orcid = orcid.replace("http://orcid.org/", "").replace("https://orcid.org/", "")
        authors.append(Author(name=name, affiliation=affiliation, orcid=orcid if orcid else None))
    return authors


def _extract_venue(item: Dict[str, Any]) -> str | None:
    container = item.get("container-title") or []
    if isinstance(container, list) and container:
        return container[0]
    if isinstance(container, str):
        return container
    return None


def _extract_url(item: Dict[str, Any]) -> str:
    doi = item.get("DOI")
    if doi:
        return f"https://doi.org/{doi}"
    return item.get("URL", "")


def parse_crossref_response(raw_json: Dict[str, Any]) -> List[Paper]:
    papers: List[Paper] = []
    items = raw_json.get("message", {}).get("items", []) or []
    for item in items:
        title_list = item.get("title", []) or []
        title = title_list[0] if title_list else ""
        if not title:
            continue
        abstract = item.get("abstract", "") or ""
        if abstract.startswith("<jats:abstract>") or abstract.startswith("<jats:p>"):
            import re
            abstract = re.sub(r"<[^>]+>", "", abstract).strip()
        doi = item.get("DOI")
        refs = item.get("reference", []) or []
        paper = Paper(
            title=title,
            authors=_extract_authors(item),
            abstract=abstract,
            year=_extract_year(item),
            venue=_extract_venue(item),
            doi=doi,
            arxiv_id=None,
            url=_extract_url(item),
            citation_count=item.get("is-referenced-by-count", 0) or 0,
            references_count=len(refs),
            source=["crossref"],
            raw={"crossref_item": item},
        )
        papers.append(paper)
    return papers
