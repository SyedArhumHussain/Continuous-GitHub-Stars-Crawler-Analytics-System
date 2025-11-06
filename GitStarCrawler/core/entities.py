"""
Core domain entities for GitStarCrawler.
These represent the business objects in our system.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Repository:
    """
    Repository entity representing a GitHub repository.
    This is the core domain model.
    """
    repo_id: int
    name: str
    owner: str
    stars: int
    forks: Optional[int] = None
    open_issues: Optional[int] = None
    last_updated: Optional[datetime] = None

    def __post_init__(self):
        """Validate repository data."""
        if self.repo_id <= 0:
            raise ValueError("repo_id must be positive")
        if self.stars < 0:
            raise ValueError("stars cannot be negative")
        if not self.name or not self.owner:
            raise ValueError("name and owner are required")


@dataclass
class CrawlState:
    """
    Represents the current state of a crawl operation.
    Used for resuming interrupted crawls.
    """
    cursor: Optional[str] = None
    repositories_processed: int = 0
    last_update: Optional[datetime] = None
    rate_limit_remaining: int = 5000
    rate_limit_reset_at: Optional[datetime] = None

    def should_wait_for_rate_limit(self) -> bool:
        """Check if we should wait due to rate limiting."""
        return self.rate_limit_remaining < 100


@dataclass
class CrawlResult:
    """
    Result of a crawl operation.
    """
    repositories: list[Repository]
    cursor: Optional[str]
    has_next_page: bool
    rate_limit_remaining: int
    rate_limit_reset_at: Optional[datetime]
