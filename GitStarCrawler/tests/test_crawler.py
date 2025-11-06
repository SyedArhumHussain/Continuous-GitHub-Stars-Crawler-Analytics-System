"""
Tests for the GitHub crawler functionality.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from core.entities import Repository, CrawlResult, CrawlState
from core.use_cases import CrawlRepositories
from infrastructure.github_client import GitHubClient


class TestRepository:
    """Test Repository entity."""

    def test_valid_repository(self):
        """Test creating a valid repository."""
        repo = Repository(
            repo_id=12345,
            name="test-repo",
            owner="testuser",
            stars=100,
            forks=10,
            open_issues=5,
        )

        assert repo.repo_id == 12345
        assert repo.name == "test-repo"
        assert repo.owner == "testuser"
        assert repo.stars == 100

    def test_invalid_repo_id(self):
        """Test that invalid repo_id raises error."""
        with pytest.raises(ValueError, match="repo_id must be positive"):
            Repository(
                repo_id=-1,
                name="test-repo",
                owner="testuser",
                stars=100,
            )

    def test_negative_stars(self):
        """Test that negative stars raises error."""
        with pytest.raises(ValueError, match="stars cannot be negative"):
            Repository(
                repo_id=12345,
                name="test-repo",
                owner="testuser",
                stars=-10,
            )

    def test_empty_name(self):
        """Test that empty name raises error."""
        with pytest.raises(ValueError, match="name and owner are required"):
            Repository(
                repo_id=12345,
                name="",
                owner="testuser",
                stars=100,
            )


class TestCrawlState:
    """Test CrawlState entity."""

    def test_should_wait_for_rate_limit(self):
        """Test rate limit detection."""
        state = CrawlState(rate_limit_remaining=50)
        assert state.should_wait_for_rate_limit() is True

        state = CrawlState(rate_limit_remaining=200)
        assert state.should_wait_for_rate_limit() is False


class TestCrawlRepositories:
    """Test CrawlRepositories use case."""

    @patch('infrastructure.github_client.GitHubClient')
    @patch('infrastructure.db_client.DatabaseClient')
    def test_execute_basic_crawl(self, mock_db, mock_github):
        """Test basic crawl execution."""
        # Setup mocks
        mock_github_instance = Mock()
        mock_db_instance = Mock()
        mock_github.return_value = mock_github_instance
        mock_db.return_value = mock_db_instance

        # Mock database responses
        mock_db_instance.load_crawl_state.return_value = None

        # Mock GitHub API responses
        mock_repos = [
            Repository(
                repo_id=i,
                name=f"repo-{i}",
                owner=f"owner-{i}",
                stars=100 - i,
            )
            for i in range(10)
        ]

        mock_github_instance.search_repositories.return_value = CrawlResult(
            repositories=mock_repos,
            cursor=None,
            has_next_page=False,
            rate_limit_remaining=5000,
            rate_limit_reset_at=datetime.now(),
        )

        mock_github_instance.get_repository_count.return_value = 10

        # Execute use case
        use_case = CrawlRepositories(mock_github_instance, mock_db_instance)
        state = use_case.execute(target_count=10, resume=False)

        # Assertions
        assert state.repositories_processed == 10
        mock_db_instance.upsert_repositories.assert_called_once()
        mock_db_instance.save_crawl_state.assert_called()


# Note: Add more comprehensive tests for:
# - Rate limiting behavior
# - Error handling and retries
# - Pagination
# - Database operations
# - CSV export
