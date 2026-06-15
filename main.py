import asyncio
import time
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aggregator import Aggregator, SortStrategy
from cache import get_search_cache, get_citation_cache
from config import settings
from fetcher import ArxivFetcher, CrossrefFetcher, SemanticScholarFetcher
from logging_config import configure_logging, get_logger
from models.paper import (
    BatchSearchRequest,
    BatchSearchQuery,
    CitationsResponse,
    FavoriteCreate,
    FavoriteRecord,
    Paper,
    PaperDetailResponse,
    ReferencesResponse,
    SearchHistoryRecord,
    SearchMeta,
    SearchResponse,
    SourceStatus,
)
from storage import get_store

configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="Paper Aggregation Search API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_fetchers = [
    ArxivFetcher(),
    CrossrefFetcher(),
    SemanticScholarFetcher(),
]
_aggregator = Aggregator(_fetchers)
_search_cache = get_search_cache()
_citation_cache = get_citation_cache()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError):
    logger.error("runtime_error", error=str(exc), path=request.url.path)
    if "All sources failed" in str(exc):
        return JSONResponse(
            status_code=502,
            content={"detail": str(exc)},
        )
    if "Semantic Scholar API key is required" in str(exc):
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/api/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    year_from: Optional[int] = Query(None, ge=1900, le=2100),
    year_to: Optional[int] = Query(None, ge=1900, le=2100),
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query("relevance", pattern="^(relevance|citations|date)$"),
    sources: Optional[str] = Query(None, description="Comma-separated list of sources: arxiv,crossref,semantic_scholar"),
):
    source_list = None
    if sources:
        source_list = [s.strip() for s in sources.split(",") if s.strip()]

    cache_key = (q, year_from, year_to, limit, sort, tuple(source_list) if source_list else None)
    cached = _search_cache.get(cache_key)
    if cached is not None:
        cached.meta.cache_hit = True
        logger.info("cache_hit_search", query=q)
        return cached

    try:
        result = await _aggregator.search(
            query=q,
            year_from=year_from,
            year_to=year_to,
            max_results=limit,
            sources=source_list,
            sort=sort,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        store = get_store()
        store.add_search_history(q, year_from, year_to)
    except Exception as exc:
        logger.warning("search_history_save_failed", error=str(exc))

    _search_cache.set(cache_key, result)
    return result


@app.get("/api/paper/{doi_or_id:path}", response_model=PaperDetailResponse)
async def get_paper(doi_or_id: str):
    papers: List[Paper] = []
    source_statuses: List[SourceStatus] = []
    errors: List[str] = []

    for fetcher in _fetchers:
        start = time.perf_counter()
        try:
            paper = await fetcher.get_paper(doi_or_id)
            duration = int((time.perf_counter() - start) * 1000)
            source_statuses.append(
                SourceStatus(
                    source=fetcher.name,
                    available=True,
                    hit_count=1 if paper else 0,
                    duration_ms=duration,
                )
            )
            if paper:
                papers.append(paper)
        except Exception as exc:
            duration = int((time.perf_counter() - start) * 1000)
            errors.append(f"{fetcher.name}: {exc}")
            source_statuses.append(
                SourceStatus(
                    source=fetcher.name,
                    available=False,
                    hit_count=0,
                    duration_ms=duration,
                    error=str(exc),
                )
            )

    if not papers:
        raise HTTPException(status_code=404, detail=f"Paper not found: {doi_or_id}. Errors: {'; '.join(errors)}")

    merged, _ = _aggregator.dedupe_and_merge(papers)
    if not merged:
        raise HTTPException(status_code=404, detail=f"Paper not found: {doi_or_id}")
    return PaperDetailResponse(data=merged[0])


@app.get("/api/paper/{doi_or_id:path}/references", response_model=ReferencesResponse)
async def get_references(doi_or_id: str, limit: int = Query(100, ge=1, le=500)):
    cache_key = ("references", doi_or_id)
    cached = _citation_cache.get(cache_key)
    if cached is not None:
        logger.info("cache_hit_references", id=doi_or_id)
        return ReferencesResponse(meta={"cache_hit": True}, data=cached[:limit])

    all_refs: List[Paper] = []
    for fetcher in _fetchers:
        try:
            refs = await fetcher.get_references(doi_or_id)
            all_refs.extend(refs)
        except Exception as exc:
            logger.warning("references_fetch_failed", source=fetcher.name, error=str(exc))

    merged_refs, dups = _aggregator.dedupe_and_merge(all_refs)
    merged_refs = sorted(merged_refs, key=lambda p: p.citation_count or 0, reverse=True)
    _citation_cache.set(cache_key, merged_refs)
    return ReferencesResponse(
        meta={"cache_hit": False, "total": len(merged_refs), "duplicates_removed": dups},
        data=merged_refs[:limit],
    )


@app.get("/api/paper/{doi_or_id:path}/citations", response_model=CitationsResponse)
async def get_citations(doi_or_id: str, limit: int = Query(100, ge=1, le=500)):
    cache_key = ("citations", doi_or_id)
    cached = _citation_cache.get(cache_key)
    if cached is not None:
        logger.info("cache_hit_citations", id=doi_or_id)
        return CitationsResponse(meta={"cache_hit": True}, data=cached[:limit])

    all_cites: List[Paper] = []
    last_error: Optional[Exception] = None
    for fetcher in _fetchers:
        try:
            cites = await fetcher.get_citations(doi_or_id)
            all_cites.extend(cites)
        except RuntimeError as exc:
            if "API key is required" in str(exc):
                raise HTTPException(status_code=400, detail=str(exc))
            last_error = exc
            logger.warning("citations_fetch_failed", source=fetcher.name, error=str(exc))
        except Exception as exc:
            last_error = exc
            logger.warning("citations_fetch_failed", source=fetcher.name, error=str(exc))

    if not all_cites and last_error:
        raise HTTPException(status_code=502, detail=str(last_error))

    merged_cites, dups = _aggregator.dedupe_and_merge(all_cites)
    merged_cites = sorted(merged_cites, key=lambda p: p.citation_count or 0, reverse=True)
    _citation_cache.set(cache_key, merged_cites)
    return CitationsResponse(
        meta={"cache_hit": False, "total": len(merged_cites), "duplicates_removed": dups},
        data=merged_cites[:limit],
    )


@app.post("/api/batch")
async def batch_search(request: BatchSearchRequest):
    async def _do_search(q: BatchSearchQuery) -> SearchResponse:
        cache_key = (q.q, q.year_from, q.year_to, q.limit, q.sort, tuple(q.sources) if q.sources else None)
        cached = _search_cache.get(cache_key)
        if cached is not None:
            cached.meta.cache_hit = True
            return cached
        result = await _aggregator.search(
            query=q.q,
            year_from=q.year_from,
            year_to=q.year_to,
            max_results=q.limit,
            sources=q.sources,
            sort=q.sort,
        )
        _search_cache.set(cache_key, result)
        return result

    tasks = [_do_search(q) for q in request.queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    responses = []
    for r in results:
        if isinstance(r, Exception):
            responses.append({"error": str(r)})
        else:
            responses.append(r.model_dump())
    return {"results": responses}


@app.get("/api/history", response_model=List[SearchHistoryRecord])
async def get_search_history(limit: int = Query(50, ge=1, le=500)):
    store = get_store()
    return store.get_search_history(limit=limit)


@app.get("/api/favorites", response_model=List[FavoriteRecord])
async def list_favorites():
    store = get_store()
    return store.get_favorites()


@app.post("/api/favorites", response_model=FavoriteRecord)
async def add_favorite(payload: FavoriteCreate):
    store = get_store()
    title = None
    try:
        resp = await get_paper(payload.doi_or_id)
        title = resp.data.title
    except Exception:
        pass
    store.add_favorite(payload.doi_or_id, paper_title=title, note=payload.note)
    favs = store.get_favorites()
    for f in favs:
        if f.doi_or_id == payload.doi_or_id:
            return f
    raise HTTPException(status_code=500, detail="Failed to add favorite")


@app.delete("/api/favorites/{doi_or_id:path}")
async def remove_favorite(doi_or_id: str):
    store = get_store()
    ok = store.remove_favorite(doi_or_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"ok": True}


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "cache": {
            "search": _search_cache.stats,
            "citation": _citation_cache.stats,
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
