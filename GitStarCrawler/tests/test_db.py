"""
Tests for database operations.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from core.entities import Repository, CrawlState
from infrastructure.db_client import DatabaseClient


class TestDatabaseClient:
    """Test DatabaseClient functionality."""

    @patch('psycopg2.connect')
    def test_connect(self, mock_connect):
        """Test database connection."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        db = DatabaseClient()
        db.connect()

        mock_connect.assert_called_once()
        assert db._conn == mock_conn

    @patch('psycopg2.connect')
    def test_context_manager(self, mock_connect):
        """Test database context manager."""
        mock_conn = Mock()
        mock_conn.closed = False
        mock_connect.return_value = mock_conn

        db = DatabaseClient()

        with db as client:
            assert client is db
            mock_connect.assert_called_once()

        mock_conn.close.assert_called_once()

    @patch('psycopg2.connect')
    def test_create_schema(self, mock_connect):
        """Test schema creation."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        db = DatabaseClient()
        db.create_schema()

        # Should execute multiple CREATE TABLE statements
        assert mock_cursor.execute.call_count >= 3
        mock_conn.commit.assert_called()

    @patch('psycopg2.connect')
    def test_upsert_repositories(self, mock_connect):
        """Test upserting repositories."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        repos = [
            Repository(
                repo_id=1,
                name="repo1",
                owner="owner1",
                stars=100,
            ),
            Repository(
                repo_id=2,
                name="repo2",
                owner="owner2",
                stars=200,
            ),
        ]

        db = DatabaseClient()
        with patch('infrastructure.db_client.execute_values') as mock_execute:
            count = db.upsert_repositories(repos)

        assert count == 2
        mock_execute.assert_called_once()
        mock_conn.commit.assert_called()

    @patch('psycopg2.connect')
    def test_save_crawl_state(self, mock_connect):
        """Test saving crawl state."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        state = CrawlState(
            cursor="test_cursor",
            repositories_processed=100,
            rate_limit_remaining=4900,
        )

        db = DatabaseClient()
        db.save_crawl_state(state)

        # Should execute UPDATE and INSERT
        assert mock_cursor.execute.call_count == 2
        mock_conn.commit.assert_called()


# Note: These are basic unit tests. For integration tests, you would:
# 1. Use pytest fixtures with a test database
# 2. Test actual database operations
# 3. Verify data integrity and constraints
# 4. Test concurrent operations
