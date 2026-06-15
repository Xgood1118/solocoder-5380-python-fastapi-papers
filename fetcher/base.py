from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from models.paper import Paper


@dataclass
class FetchResult:
    source: str
    papers: List[Paper] = field(default_factory=list)
    available: bool = True
    error: Optional[str] = None
    duration_ms: int = 0

    @property
    def hit_count(self) -> int:
        return len(self.papers)


class BaseFetcher(ABC):
    name: str = "base"

    @abstractmethod
    async def search(
        self,
        query: str,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        max_results: int = 20,
    ) -> FetchResult: ...

    @abstractmethod
    async def get_paper(self, doi_or_id: str) -> Optional[Paper]:
        return None

    @abstractmethod
    async def get_references(self, doi_or_id: str) -> List[Paper]:
        return []

    @abstractmethod
    async def get_citations(self, doi_or_id: str) -> List[Paper]:
        return []
