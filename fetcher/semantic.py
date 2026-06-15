import time
from typing import List, Optional

import httpx

from config import settings
from fetcher.base import BaseFetcher, FetchResult
from limiter import get_limiter
from logging_config import get_logger
from models.paper import Paper
from parser import parse_semantic_response, parse_semantic_paper_detail

logger = get_logger(__name__)

SEMANTIC_API = "https://api.semanticscholar.org/graph/v1"


class SemanticScholarFetcher(BaseFetcher):
    name = "semantic_scholar"

    def __init__(self):
        headers = {}
        if settings.semantic_scholar_api_key:
            headers["x-api-key"] = settings.semantic_scholar_api_key
        self._client = httpx.AsyncClient(timeout=settings.request_timeout, headers=headers)
        self._limiter = get_limiter("semantic_scholar")
        self._api_key = settings.semantic_scholar_api_key

    def _check_api_key_required(self, need_key: bool = False) -> None:
        if need_key and not self._api_key:
            raise RuntimeError(
                "Semantic Scholar API key is required for this operation. "
                "Please set SEMANTIC_SCHOLAR_API_KEY environment variable."
            )

    def _default_fields(self) -> str:
        return ",".join([
            "paperId",
            "externalIds",
            "url",
            "title",
            "abstract",
            "venue",
            "year",
            "referenceCount",
            "citationCount",
            "authors",
            "publicationDate",
            "doi",
        ])

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
                "limit": max_results,
                "fields": self._default_fields(),
            }
            if year_from:
                params["year"] = f"{year_from}-"
            if year_to:
                if "year" in params:
                    params["year"] = params["year"] + str(year_to)
                else:
                    params["year"] = f"-{year_to}"
            logger.info("semantic_fetch_start", query=query, params=params)
            resp = await self._client.get(f"{SEMANTIC_API}/paper/search", params=params)
            resp.raise_for_status()
            data = resp.json()
            papers = parse_semantic_response(data)
            result.papers = papers
            logger.info(
                "semantic_fetch_done",
                query=query,
                hit_count=result.hit_count,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:
            result.available = False
            result.error = str(exc)
            logger.error("semantic_fetch_error", query=query, error=str(exc))
        finally:
            result.duration_ms = int((time.perf_counter() - start) * 1000)
        return result

    async def get_paper(self, doi_or_id: str) -> Optional[Paper]:
        try:
            await self._limiter.acquire()
            if doi_or_id.lower().startswith("10."):
                pid = f"DOI:{doi_or_id}"
            elif doi_or_id.lower().startswith("arxiv:") or "/" not in doi_or_id and "." in doi_or_id:
                pid = f"ARXIV:{doi_or_id.replace('arxiv:', '')}"
            else:
                pid = doi_or_id
            params = {"fields": self._default_fields()}
            resp = await self._client.get(f"{SEMANTIC_API}/paper/{pid}", params=params)
            resp.raise_for_status()
            data = resp.json()
            return parse_semantic_paper_detail(data)
        except Exception as exc:
            logger.error("semantic_get_paper_error", id=doi_or_id, error=str(exc))
            return None

    async def get_references(self, doi_or_id: str) -> List[Paper]:
        try:
            await self._limiter.acquire()
            if doi_or_id.lower().startswith("10."):
                pid = f"DOI:{doi_or_id}"
            elif doi_or_id.lower().startswith("arxiv:") or "/" not in doi_or_id and "." in doi_or_id:
                pid = f"ARXIV:{doi_or_id.replace('arxiv:', '')}"
            else:
                pid = doi_or_id
            params = {"fields": self._default_fields(), "limit": 100}
            resp = await self._client.get(f"{SEMANTIC_API}/paper/{pid}/references", params=params)
            resp.raise_for_status()
            data = resp.json()
            cited_papers = [item.get("citedPaper", {}) for item in data.get("data", []) if item.get("citedPaper")]
            return parse_semantic_response({"data": cited_papers})
        except Exception as exc:
            logger.error("semantic_get_references_error", id=doi_or_id, error=str(exc))
            return []

    async def get_citations(self, doi_or_id: str) -> List[Paper]:
        self._check_api_key_required(need_key=True)
        try:
            await self._limiter.acquire()
            if doi_or_id.lower().startswith("10."):
                pid = f"DOI:{doi_or_id}"
            elif doi_or_id.lower().startswith("arxiv:") or "/" not in doi_or_id and "." in doi_or_id:
                pid = f"ARXIV:{doi_or_id.replace('arxiv:', '')}"
            else:
                pid = doi_or_id
            params = {"fields": self._default_fields(), "limit": 100}
            resp = await self._client.get(f"{SEMANTIC_API}/paper/{pid}/citations", params=params)
            resp.raise_for_status()
            data = resp.json()
            citing_papers = [item.get("citingPaper", {}) for item in data.get("data", []) if item.get("citingPaper")]
            return parse_semantic_response({"data": citing_papers})
        except Exception as exc:
            logger.error("semantic_get_citations_error", id=doi_or_id, error=str(exc))
            raise
