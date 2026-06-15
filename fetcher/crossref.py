import time
from typing import List, Optional

import httpx

from config import settings
from fetcher.base import BaseFetcher, FetchResult
from limiter import get_limiter
from logging_config import get_logger
from models.paper import Paper
from parser import parse_crossref_response

logger = get_logger(__name__)

CROSSREF_API = "https://api.crossref.org/works"


class CrossrefFetcher(BaseFetcher):
    name = "crossref"

    def __init__(self):
        headers = {}
        if settings.crossref_mailto:
            headers["User-Agent"] = f"PaperSearch/1.0 (mailto:{settings.crossref_mailto})"
        self._client = httpx.AsyncClient(timeout=settings.request_timeout, headers=headers)
        self._limiter = get_limiter("crossref")

    async def search(
        self,
        query: str,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        max_results: int = 20,
    ) -> FetchResult:
        start = time.perf_counter()
        result = FetchResult(source=self.name)
        try:
            await self._limiter.acquire()
            params: dict = {
                "query": query,
                "rows": max_results,
            }
            if year_from:
                params["filter"] = f"from-pub-date:{year_from}-01-01"
            if year_to:
                f = params.get("filter", "")
                if f:
                    params["filter"] = f + f",until-pub-date:{year_to}-12-31"
                else:
                    params["filter"] = f"until-pub-date:{year_to}-12-31"
            logger.info("crossref_fetch_start", query=query, params=params)
            resp = await self._client.get(CROSSREF_API, params=params)
            resp.raise_for_status()
            data = resp.json()
            papers = parse_crossref_response(data)
            result.papers = papers
            logger.info(
                "crossref_fetch_done",
                query=query,
                hit_count=result.hit_count,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:
            result.available = False
            result.error = str(exc)
            logger.error("crossref_fetch_error", query=query, error=str(exc))
        finally:
            result.duration_ms = int((time.perf_counter() - start) * 1000)
        return result

    async def get_paper(self, doi_or_id: str) -> Optional[Paper]:
        try:
            await self._limiter.acquire()
            resp = await self._client.get(f"{CROSSREF_API}/{doi_or_id}")
            resp.raise_for_status()
            data = {"message": {"items": [resp.json().get("message", {})]}}
            papers = parse_crossref_response(data)
            return papers[0] if papers else None
        except Exception as exc:
            logger.error("crossref_get_paper_error", id=doi_or_id, error=str(exc))
            return None

    async def get_references(self, doi_or_id: str) -> List[Paper]:
        try:
            await self._limiter.acquire()
            resp = await self._client.get(f"{CROSSREF_API}/{doi_or_id}")
            resp.raise_for_status()
            data = resp.json()
            message = data.get("message", {})
            refs = message.get("reference", []) or []
            papers: List[Paper] = []
            for ref in refs:
                doi = ref.get("DOI")
                title = ref.get("article-title") or ref.get("series-title") or ""
                if doi or title:
                    papers.append(
                        Paper(
                            title=title or doi or "",
                            doi=doi,
                            url=f"https://doi.org/{doi}" if doi else "",
                            year=None,
                            authors=[],
                            source=["crossref"],
                            raw={"crossref_ref": ref},
                        )
                    )
            return papers
        except Exception as exc:
            logger.error("crossref_get_references_error", id=doi_or_id, error=str(exc))
            return []

    async def get_citations(self, doi_or_id: str) -> List[Paper]:
        return []
