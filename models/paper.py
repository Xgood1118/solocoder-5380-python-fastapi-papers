from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict


class Author(BaseModel):
    name: str
    affiliation: Optional[str] = None
    orcid: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class Paper(BaseModel):
    title: str
    authors: List[Author] = Field(default_factory=list)
    abstract: str = ""
    year: Optional[int] = None
    venue: Optional[str] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    url: Optional[str] = None
    citation_count: int = 0
    references_count: int = 0
    source: List[str] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    raw: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True)


class SourceStatus(BaseModel):
    source: str
    available: bool
    hit_count: int = 0
    duration_ms: int = 0
    error: Optional[str] = None


class SearchMeta(BaseModel):
    total: int
    source_status: List[SourceStatus]
    duplicates_removed: int
    duration_ms: int
    cache_hit: bool = False
    sort: str


class SearchResponse(BaseModel):
    meta: SearchMeta
    data: List[Paper]


class BatchSearchQuery(BaseModel):
    q: str
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    limit: int = 20
    sort: str = "relevance"
    sources: Optional[List[str]] = None


class BatchSearchRequest(BaseModel):
    queries: List[BatchSearchQuery]


class PaperDetailResponse(BaseModel):
    data: Paper


class CitationsResponse(BaseModel):
    meta: Dict[str, Any]
    data: List[Paper]


class ReferencesResponse(BaseModel):
    meta: Dict[str, Any]
    data: List[Paper]


class FavoriteCreate(BaseModel):
    doi_or_id: str
    note: Optional[str] = None


class FavoriteRecord(BaseModel):
    id: int
    doi_or_id: str
    paper_title: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime


class SearchHistoryRecord(BaseModel):
    id: int
    query: str
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    created_at: datetime
