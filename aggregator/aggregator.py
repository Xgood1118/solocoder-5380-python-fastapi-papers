import asyncio
import re
import string
import time
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from logging_config import get_logger
from models.paper import Paper, SourceStatus, SearchMeta, SearchResponse
from fetcher.base import FetchResult

logger = get_logger(__name__)


class SortStrategy:
    CITATIONS = "citations"
    RELEVANCE = "relevance"
    DATE = "date"


def _normalize_title(title: str) -> str:
    if not title:
        return ""
    title = title.lower()
    title = title.translate(str.maketrans(string.punctuation, " " * len(string.punctuation)))
    title = re.sub(r"\s+", " ", title).strip()
    return title


def _titles_similar(a: str, b: str, threshold: float = 0.92) -> bool:
    na = _normalize_title(a)
    nb = _normalize_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def _first_author_lastname(paper: Paper) -> str:
    if not paper.authors:
        return ""
    name = paper.authors[0].name or ""
    parts = name.strip().split()
    if not parts:
        return ""
    return _normalize_title(parts[-1])


def _completeness_score(paper: Paper) -> int:
    score = 0
    if paper.title:
        score += 2
    if paper.abstract and len(paper.abstract) > 50:
        score += 3
    if paper.authors:
        score += 1
    if paper.doi:
        score += 2
    if paper.arxiv_id:
        score += 1
    if paper.venue:
        score += 1
    if paper.year:
        score += 1
    return score


def _merge_papers(base: Paper, other: Paper) -> Paper:
    new_authors = list(base.authors)
    seen_names = {_normalize_title(a.name) for a in base.authors}
    for a in other.authors:
        if _normalize_title(a.name) not in seen_names:
            new_authors.append(a)
            seen_names.add(_normalize_title(a.name))
    return Paper(
        title=base.title or other.title,
        authors=new_authors,
        abstract=base.abstract if len(base.abstract or "") >= len(other.abstract or "") else other.abstract,
        year=base.year or other.year,
        venue=base.venue or other.venue,
        doi=base.doi or other.doi,
        arxiv_id=base.arxiv_id or other.arxiv_id,
        url=base.url or other.url,
        citation_count=max(base.citation_count or 0, other.citation_count or 0),
        references_count=max(base.references_count or 0, other.references_count or 0),
        source=sorted(set(base.source + other.source)),
        fetched_at=max(base.fetched_at, other.fetched_at),
        raw={**base.raw, **other.raw},
    )


def _relevance_score(paper: Paper, query: str) -> float:
    if not query:
        return 0.0
    q = query.lower()
    title = (paper.title or "").lower()
    abstract = (paper.abstract or "").lower()
    score = 0.0
    q_terms = [t for t in re.split(r"\W+", q) if t]
    if not q_terms:
        return 0.0
    for term in q_terms:
        if term in title:
            score += 3.0
        if term in abstract:
            score += 1.0
    return score


class Aggregator:
    def __init__(self, fetchers):
        self._fetchers = fetchers

    def dedupe_and_merge(self, all_papers: List[Paper]) -> Tuple[List[Paper], int]:
        by_doi: Dict[str, Paper] = {}
        no_doi_papers: List[Paper] = []
        duplicates_removed = 0

        for paper in all_papers:
            if paper.doi:
                key = paper.doi.lower().strip()
                if key in by_doi:
                    by_doi[key] = _merge_papers(by_doi[key], paper)
                    duplicates_removed += 1
                else:
                    by_doi[key] = paper
            else:
                no_doi_papers.append(paper)

        merged: List[Paper] = []
        for paper in no_doi_papers:
            matched = False
            for i, existing in enumerate(merged):
                if not _titles_similar(existing.title, paper.title):
                    continue
                year_ok = (
                    not existing.year
                    or not paper.year
                    or abs(existing.year - paper.year) <= 1
                )
                fa_existing = _first_author_lastname(existing)
                fa_paper = _first_author_lastname(paper)
                first_author_ok = (
                    not fa_existing
                    or not fa_paper
                    or fa_existing == fa_paper
                )
                if not (year_ok and first_author_ok):
                    continue
                if _completeness_score(paper) > _completeness_score(existing):
                    merged[i] = _merge_papers(paper, existing)
                else:
                    merged[i] = _merge_papers(existing, paper)
                duplicates_removed += 1
                matched = True
                break
            if not matched:
                merged.append(paper)

        result = list(by_doi.values())
        result.extend(merged)
        return result, duplicates_removed

    def sort_papers(
        self, papers: List[Paper], strategy: str, query: Optional[str] = None
    ) -> List[Paper]:
        if strategy == SortStrategy.CITATIONS:
            return sorted(papers, key=lambda p: p.citation_count or 0, reverse=True)
        elif strategy == SortStrategy.DATE:
            return sorted(papers, key=lambda p: p.year or 0, reverse=True)
        else:
            return sorted(
                papers,
                key=lambda p: (
                    _relevance_score(p, query or ""),
                    p.citation_count or 0,
                    p.year or 0,
                ),
                reverse=True,
            )

    async def search(
        self,
        query: str,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        max_results: int = 20,
        sources: Optional[List[str]] = None,
        sort: str = SortStrategy.RELEVANCE,
    ) -> SearchResponse:
        start = time.perf_counter()
        selected_fetchers = [
            f for f in self._fetchers if sources is None or f.name in sources
        ]
        tasks = [
            f.search(query, year_from, year_to, max_results) for f in selected_fetchers
        ]
        results: List[FetchResult] = []
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            logger.warning("aggregate_search_timeout", query=query)

        normalized_results: List[FetchResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                name = selected_fetchers[i].name if i < len(selected_fetchers) else "unknown"
                normalized_results.append(
                    FetchResult(source=name, available=False, error=str(r))
                )
            else:
                normalized_results.append(r)

        all_papers: List[Paper] = []
        source_statuses: List[SourceStatus] = []
        for r in normalized_results:
            all_papers.extend(r.papers)
            source_statuses.append(
                SourceStatus(
                    source=r.source,
                    available=r.available,
                    hit_count=r.hit_count,
                    duration_ms=r.duration_ms,
                    error=r.error,
                )
            )

        merged_papers, duplicates_removed = self.dedupe_and_merge(all_papers)
        sorted_papers = self.sort_papers(merged_papers, sort, query)
        sorted_papers = sorted_papers[:max_results]
        duration_ms = int((time.perf_counter() - start) * 1000)

        all_unavailable = source_statuses and all(not s.available for s in source_statuses)
        if all_unavailable:
            errors = "; ".join([f"{s.source}: {s.error}" for s in source_statuses if s.error])
            raise RuntimeError(f"All sources failed: {errors}")

        return SearchResponse(
            meta=SearchMeta(
                total=len(sorted_papers),
                source_status=source_statuses,
                duplicates_removed=duplicates_removed,
                duration_ms=duration_ms,
                cache_hit=False,
                sort=sort,
            ),
            data=sorted_papers,
        )
