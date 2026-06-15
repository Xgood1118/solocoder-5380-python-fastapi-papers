from typing import List, Dict, Any, Optional

from models.paper import Paper, Author


def _extract_year(item: Dict[str, Any]) -> int | None:
    year = item.get("year")
    if isinstance(year, int):
        return year
    pub_date = item.get("publicationDate") or item.get("publication_date")
    if pub_date and isinstance(pub_date, str):
        parts = pub_date.split("-")
        if parts and parts[0].isdigit():
            return int(parts[0])
    return None


def _extract_authors(item: Dict[str, Any]) -> List[Author]:
    authors: List[Author] = []
    for a in item.get("authors", []) or []:
        name = a.get("name", "") or ""
        if not name:
            continue
        orcid = None
        ids = a.get("authorId") or a.get("externalIds", {}) or {}
        if isinstance(ids, dict):
            orcid = ids.get("ORCID")
        authors.append(Author(name=name, orcid=orcid))
    return authors


def _extract_venue(item: Dict[str, Any]) -> str | None:
    venue = item.get("venue") or item.get("journal")
    if isinstance(venue, dict):
        return venue.get("name")
    return venue if isinstance(venue, str) else None


def _extract_external_ids(item: Dict[str, Any]) -> Dict[str, str]:
    ext = item.get("externalIds", {}) or {}
    result = {}
    for k, v in ext.items():
        if isinstance(v, str):
            result[k] = v
        elif isinstance(v, list) and v:
            result[k] = v[0]
    return result


def _extract_arxiv_id(item: Dict[str, Any], ext: Dict[str, str]) -> Optional[str]:
    if ext.get("ArXiv"):
        return ext["ArXiv"]
    pid = item.get("paperId") or item.get("id") or ""
    if pid and "." in pid and len(pid) < 20:
        return pid
    return None


def _extract_doi(item: Dict[str, Any], ext: Dict[str, str]) -> Optional[str]:
    if ext.get("DOI"):
        return ext["DOI"]
    doi = item.get("doi")
    if doi:
        return doi
    return None


def parse_semantic_response(raw_json: Dict[str, Any]) -> List[Paper]:
    papers: List[Paper] = []
    data = raw_json.get("data", []) or []
    for item in data:
        title = item.get("title", "") or ""
        if not title:
            continue
        ext = _extract_external_ids(item)
        doi = _extract_doi(item, ext)
        arxiv_id = _extract_arxiv_id(item, ext)
        url = ""
        if doi:
            url = f"https://doi.org/{doi}"
        elif arxiv_id:
            url = f"https://arxiv.org/abs/{arxiv_id}"
        else:
            pid = item.get("paperId") or item.get("id") or ""
            if pid:
                url = f"https://www.semanticscholar.org/paper/{pid}"
        paper = Paper(
            title=title,
            authors=_extract_authors(item),
            abstract=item.get("abstract", "") or "",
            year=_extract_year(item),
            venue=_extract_venue(item),
            doi=doi,
            arxiv_id=arxiv_id,
            url=url,
            citation_count=item.get("citationCount", 0) or 0,
            references_count=item.get("referenceCount", 0) or 0,
            source=["semantic_scholar"],
            raw={"semantic_item": item},
        )
        papers.append(paper)
    return papers


def parse_semantic_paper_detail(item: Dict[str, Any]) -> Optional[Paper]:
    if not item:
        return None
    title = item.get("title", "") or ""
    if not title:
        return None
    ext = _extract_external_ids(item)
    doi = _extract_doi(item, ext)
    arxiv_id = _extract_arxiv_id(item, ext)
    url = ""
    if doi:
        url = f"https://doi.org/{doi}"
    elif arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"
    else:
        pid = item.get("paperId") or item.get("id") or ""
        if pid:
            url = f"https://www.semanticscholar.org/paper/{pid}"
    return Paper(
        title=title,
        authors=_extract_authors(item),
        abstract=item.get("abstract", "") or "",
        year=_extract_year(item),
        venue=_extract_venue(item),
        doi=doi,
        arxiv_id=arxiv_id,
        url=url,
        citation_count=item.get("citationCount", 0) or 0,
        references_count=item.get("referenceCount", 0) or 0,
        source=["semantic_scholar"],
        raw={"semantic_item": item},
    )
