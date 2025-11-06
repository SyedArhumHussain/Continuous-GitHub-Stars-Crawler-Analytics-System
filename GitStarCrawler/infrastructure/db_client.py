"""
PostgreSQL database client for storing and retrieving repository data.
"""

import logging
import os
from typing import Optional, List
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values
from psycopg2.extensions import connection

from core.entities import Repository, CrawlState

logger = logging.getLogger(__name__)


class DatabaseClient:
    """
    PostgreSQL database client with connection pooling and UPSERT support.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "github_data",
        user: str = "github",
        password: str = "github",
    ):
        """
        Initialize database client.

        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
        """
        # Allow environment variable overrides
        self.host = os.environ.get("DB_HOST", host)
        self.port = int(os.environ.get("DB_PORT", port))
        self.database = os.environ.get("DB_NAME", database)
        self.user = os.environ.get("DB_USER", user)
        self.password = os.environ.get("DB_PASSWORD", password)

        self._conn: Optional[connection] = None

    def connect(self):
        """Establish database connection."""
        if self._conn is None or self._conn.closed:
            logger.info(
                f"Connecting to database {self.database} at {self.host}:{self.port}"
            )
            self._conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
            )
            logger.info("Database connection established")

    def close(self):
        """Close database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("Database connection closed")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def create_schema(self):
        """
        Create database schema if it doesn't exist.
        Includes tables for repositories and crawl state.
        """
        self.connect()

        with self._conn.cursor() as cursor:
            # Create repositories table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS repositories (
                    id SERIAL PRIMARY KEY,
                    repo_id BIGINT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    stars INTEGER NOT NULL,
                    forks INTEGER,
                    open_issues INTEGER,
                    last_updated TIMESTAMP DEFAULT NOW(),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # Create indexes for efficient queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_repo_id
                ON repositories(repo_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_owner_name
                ON repositories(owner, name)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_stars
                ON repositories(stars DESC)
            """)

            # Create crawl_state table to track progress
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS crawl_state (
                    id SERIAL PRIMARY KEY,
                    cursor TEXT,
                    repositories_processed INTEGER DEFAULT 0,
                    last_update TIMESTAMP DEFAULT NOW(),
                    rate_limit_remaining INTEGER,
                    rate_limit_reset_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)

            self._conn.commit()
            logger.info("Database schema created successfully")

    def upsert_repositories(self, repositories: List[Repository]) -> int:
        """
        Insert or update repositories using UPSERT (ON CONFLICT).

        Args:
            repositories: List of Repository entities

        Returns:
            Number of repositories inserted/updated
        """
        if not repositories:
            return 0

        self.connect()

        # Prepare data for batch insert
        values = [
            (
                repo.repo_id,
                repo.name,
                repo.owner,
                repo.stars,
                repo.forks,
                repo.open_issues,
                repo.last_updated or datetime.now(),
            )
            for repo in repositories
        ]

        with self._conn.cursor() as cursor:
            execute_values(
                cursor,
                """
                INSERT INTO repositories
                    (repo_id, name, owner, stars, forks, open_issues, last_updated)
                VALUES %s
                ON CONFLICT (repo_id)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    owner = EXCLUDED.owner,
                    stars = EXCLUDED.stars,
                    forks = EXCLUDED.forks,
                    open_issues = EXCLUDED.open_issues,
                    last_updated = EXCLUDED.last_updated
                """,
                values,
            )

            self._conn.commit()

        logger.info(f"Upserted {len(repositories)} repositories")
        return len(repositories)

    def save_crawl_state(self, state: CrawlState):
        """
        Save current crawl state for resuming.

        Args:
            state: CrawlState entity
        """
        self.connect()

        with self._conn.cursor() as cursor:
            # Deactivate previous states
            cursor.execute("UPDATE crawl_state SET is_active = FALSE")

            # Insert new state
            cursor.execute(
                """
                INSERT INTO crawl_state
                    (cursor, repositories_processed, last_update,
                     rate_limit_remaining, rate_limit_reset_at, is_active)
                VALUES (%s, %s, %s, %s, %s, TRUE)
                """,
                (
                    state.cursor,
                    state.repositories_processed,
                    state.last_update or datetime.now(),
                    state.rate_limit_remaining,
                    state.rate_limit_reset_at,
                ),
            )

            self._conn.commit()

        logger.info(
            f"Saved crawl state: {state.repositories_processed} processed, "
            f"cursor: {state.cursor[:20] if state.cursor else 'None'}..."
        )

    def load_crawl_state(self) -> Optional[CrawlState]:
        """
        Load the most recent active crawl state.

        Returns:
            CrawlState if found, None otherwise
        """
        self.connect()

        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT cursor, repositories_processed, last_update,
                       rate_limit_remaining, rate_limit_reset_at
                FROM crawl_state
                WHERE is_active = TRUE
                ORDER BY last_update DESC
                LIMIT 1
                """
            )

            row = cursor.fetchone()

            if row:
                return CrawlState(
                    cursor=row[0],
                    repositories_processed=row[1],
                    last_update=row[2],
                    rate_limit_remaining=row[3],
                    rate_limit_reset_at=row[4],
                )

        return None

    def get_repository_count(self) -> int:
        """
        Get total number of repositories in database.

        Returns:
            Repository count
        """
        self.connect()

        with self._conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM repositories")
            return cursor.fetchone()[0]

    def get_top_repositories(self, limit: int = 100) -> List[Repository]:
        """
        Get top repositories by star count.

        Args:
            limit: Maximum number of repositories to return

        Returns:
            List of Repository entities
        """
        self.connect()

        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT repo_id, name, owner, stars, forks, open_issues, last_updated
                FROM repositories
                ORDER BY stars DESC
                LIMIT %s
                """,
                (limit,),
            )

            repositories = []
            for row in cursor.fetchall():
                repo = Repository(
                    repo_id=row[0],
                    name=row[1],
                    owner=row[2],
                    stars=row[3],
                    forks=row[4],
                    open_issues=row[5],
                    last_updated=row[6],
                )
                repositories.append(repo)

            return repositories

    def export_to_csv(self, output_path: str):
        """
        Export all repositories to CSV file.

        Args:
            output_path: Path to output CSV file
        """
        self.connect()

        with self._conn.cursor() as cursor:
            with open(output_path, "w", encoding="utf-8") as f:
                # Write CSV header
                f.write("repo_id,name,owner,stars,forks,open_issues,last_updated\n")

                # Use COPY for efficient export
                cursor.copy_expert(
                    """
                    COPY (
                        SELECT repo_id, name, owner, stars, forks,
                               open_issues, last_updated
                        FROM repositories
                        ORDER BY stars DESC
                    ) TO STDOUT WITH CSV
                    """,
                    f,
                )

        logger.info(f"Exported repositories to {output_path}")
