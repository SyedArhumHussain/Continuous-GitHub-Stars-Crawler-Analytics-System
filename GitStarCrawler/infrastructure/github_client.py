"""
GitHub GraphQL API client with rate limiting and pagination support.
"""

import logging
import os
from typing import Optional
from datetime import datetime
import requests

from core.entities import Repository, CrawlResult
from infrastructure.retry_utils import (
    exponential_backoff,
    RateLimiter,
    RateLimitExceeded
)

logger = logging.getLogger(__name__)


class GitHubClient:
    """
    Client for interacting with GitHub's GraphQL API.
    Handles authentication, rate limiting, and pagination.
    """

    GRAPHQL_ENDPOINT = "https://api.github.com/graphql"

    # GraphQL query to fetch repositories with star counts
    SEARCH_QUERY = """
    query SearchRepositories($query: String!, $cursor: String, $perPage: Int!) {
      search(query: $query, type: REPOSITORY, first: $perPage, after: $cursor) {
        repositoryCount
        pageInfo {
          hasNextPage
          endCursor
        }
        edges {
          node {
            ... on Repository {
              databaseId
              name
              owner {
                login
              }
              stargazerCount
              forkCount
              issues(states: OPEN) {
                totalCount
              }
            }
          }
        }
      }
      rateLimit {
        remaining
        resetAt
      }
    }
    """

    def __init__(self, token: Optional[str] = None, per_page: int = 100):
        """
        Initialize GitHub client.

        Args:
            token: GitHub personal access token (or uses GITHUB_TOKEN env var)
            per_page: Number of repositories to fetch per page (max 100)
        """
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError(
                "GitHub token required. Set GITHUB_TOKEN environment variable "
                "or pass token parameter."
            )

        self.per_page = min(per_page, 100)  # GitHub max is 100
        self.rate_limiter = RateLimiter()

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @exponential_backoff(max_retries=5, base_delay=2.0, max_delay=120.0)
    def _make_request(self, query: str, variables: dict) -> dict:
        """
        Make a GraphQL request with retry logic.

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            Response JSON

        Raises:
            RateLimitExceeded: If rate limit is hit
            requests.HTTPError: For other HTTP errors
        """
        self.rate_limiter.record_request()

        response = requests.post(
            self.GRAPHQL_ENDPOINT,
            json={"query": query, "variables": variables},
            headers=self.headers,
            timeout=30,
        )

        # Check for rate limit in response
        data = response.json()

        if "errors" in data:
            error_messages = [e.get("message", "") for e in data["errors"]]
            error_str = "; ".join(error_messages)

            # Check for rate limit error
            if any("rate limit" in msg.lower() for msg in error_messages):
                # Try to extract reset time from rate limit info if available
                if "data" in data and data["data"] and "rateLimit" in data["data"]:
                    reset_at_str = data["data"]["rateLimit"]["resetAt"]
                    reset_at = datetime.fromisoformat(
                        reset_at_str.replace("Z", "+00:00")
                    )
                    raise RateLimitExceeded(reset_at)
                else:
                    # Default to 1 hour from now
                    from datetime import timedelta
                    reset_at = datetime.now() + timedelta(hours=1)
                    raise RateLimitExceeded(reset_at)

            logger.error(f"GraphQL errors: {error_str}")
            raise Exception(f"GraphQL query failed: {error_str}")

        response.raise_for_status()
        return data

    def search_repositories(
        self,
        query: str = "stars:>1",
        cursor: Optional[str] = None,
    ) -> CrawlResult:
        """
        Search for repositories using GitHub's search API.

        Args:
            query: GitHub search query (default: repositories with >1 star)
            cursor: Pagination cursor for continuing from previous results

        Returns:
            CrawlResult with repositories and pagination info
        """
        variables = {
            "query": query,
            "cursor": cursor,
            "perPage": self.per_page,
        }

        logger.info(
            f"Fetching repositories (cursor: {cursor[:20] if cursor else 'None'}...)"
        )

        data = self._make_request(self.SEARCH_QUERY, variables)

        # Extract rate limit info
        rate_limit = data["data"]["rateLimit"]
        remaining = rate_limit["remaining"]
        reset_at_str = rate_limit["resetAt"]
        reset_at = datetime.fromisoformat(reset_at_str.replace("Z", "+00:00"))

        # Update rate limiter
        self.rate_limiter.update_from_headers(remaining, reset_at)
        self.rate_limiter.wait_if_needed(remaining)

        # Extract search results
        search = data["data"]["search"]
        page_info = search["pageInfo"]
        edges = search["edges"]

        repositories = []
        for edge in edges:
            node = edge["node"]

            # Skip if databaseId is None (can happen for deleted repos)
            if not node.get("databaseId"):
                continue

            repo = Repository(
                repo_id=node["databaseId"],
                name=node["name"],
                owner=node["owner"]["login"],
                stars=node["stargazerCount"],
                forks=node.get("forkCount"),
                open_issues=node["issues"]["totalCount"],
                last_updated=datetime.now(),
            )
            repositories.append(repo)

        logger.info(
            f"Fetched {len(repositories)} repositories. "
            f"Rate limit: {remaining} remaining, resets at {reset_at}"
        )

        return CrawlResult(
            repositories=repositories,
            cursor=page_info.get("endCursor"),
            has_next_page=page_info.get("hasNextPage", False),
            rate_limit_remaining=remaining,
            rate_limit_reset_at=reset_at,
        )

    def get_repository_count(self, query: str = "stars:>1") -> int:
        """
        Get the total count of repositories matching the query.

        Args:
            query: GitHub search query

        Returns:
            Total repository count
        """
        variables = {
            "query": query,
            "cursor": None,
            "perPage": 1,  # We only need the count
        }

        data = self._make_request(self.SEARCH_QUERY, variables)
        return data["data"]["search"]["repositoryCount"]
