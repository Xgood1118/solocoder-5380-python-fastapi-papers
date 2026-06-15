import time
from typing import List, Optional

import httpx

from config import settings
from fetcher.base import BaseFetcher, FetchResult
from limiter import get_limiter
from logging_config import get_logger
from models.paper import Paper
from parser import parse_arxiv_response

logger = get_logger(__name__)

ARXIV_API = "https://export.arxiv.org/api/query"


class ArxivFetcher(BaseFetcher):
    name = "arxiv"

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=settings.request_timeout)
        self._limiter = get_limiter("arxiv")

    async def _build_query(self, query: str, year_from: Optional[int], year_to: Optional[int]) -> str:
        parts = [f"all:{query}"]
        if year_from or year_to:
            yf = year_from if year_from else 1900
            yt = year_to if year_to else 9999
            parts.append(f"submittedDate:[{yf}01010000 TO {yt}12312359]")
        return " AND ".join(parts)

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
            search_query = await self._build_query(query, year_from, year_to)
            params = {
                "search_query": search_query,
                "start": 0,
                "max_results": max_results,
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
            logger.info("arxiv_fetch_start", query=query, params=params)
            resp = await self._client.get(ARXIV_API, params=params)
            resp.raise_for_status()
            papers = parse_arxiv_response(resp.text)
            result.papers = papers
            logger.info(
                "arxiv_fetch_done",
                query=query,
                hit_count=result.hit_count,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:
            result.available = False
            result.error = str(exc)
            logger.error("arxiv_fetch_error", query=query, error=str(exc))
        finally:
            result.duration_ms = int((time.perf_counter() - start) * 1000)
        return result

    async def get_paper(self, doi_or_id: str) -> Optional[Paper]:
        try:
            await self._limiter.acquire()
            params = {"id_list": doi_or_id}
            resp = await self._client.get(ARXIV_API, params=params)
            resp.raise_for_status()
            papers = parse_arxiv_response(resp.text)
            return papers[0] if papers else None
        except Exception as exc:
            logger.error("arxiv_get_paper_error", id=doi_or_id, error=str(exc))
            return None

    async def get_references(self, doi_or_id: str) -> List[Paper]:
        return []

    async def get_citations(self, doi_or_id: str) -> List[Paper]:
        return []
