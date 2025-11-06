"""
Business logic / use cases for crawling GitHub repositories.
This layer orchestrates the interaction between GitHub API and database.
"""

import logging
from typing import Optional
from datetime import datetime

from core.entities import CrawlState
from infrastructure.github_client import GitHubClient
from infrastructure.db_client import DatabaseClient

logger = logging.getLogger(__name__)


class CrawlRepositories:
    """
    Use case for crawling GitHub repositories and storing them in the database.
    Handles resumption, progress tracking, and error recovery.
    """

    def __init__(self, github_client: GitHubClient, db_client: DatabaseClient):
        """
        Initialize the use case.

        Args:
            github_client: GitHub API client
            db_client: Database client
        """
        self.github = github_client
        self.db = db_client

    def execute(
        self,
        target_count: int = 100000,
        search_query: str = "stars:>1",
        resume: bool = True,
    ) -> CrawlState:
        """
        Execute the crawling process.

        Args:
            target_count: Target number of repositories to crawl
            search_query: GitHub search query
            resume: Whether to resume from previous crawl state

        Returns:
            Final crawl state
        """
        # Initialize or resume crawl state
        if resume:
            state = self.db.load_crawl_state()
            if state:
                logger.info(
                    f"Resuming crawl from {state.repositories_processed} repositories"
                )
            else:
                state = CrawlState()
                logger.info("Starting new crawl")
        else:
            state = CrawlState()
            logger.info("Starting new crawl (resume disabled)")

        try:
            # Get total available repositories (for logging)
            try:
                total_available = self.github.get_repository_count(search_query)
                logger.info(
                    f"Total repositories matching query: {total_available:,}"
                )
            except Exception as e:
                logger.warning(f"Could not get repository count: {e}")
                total_available = None

            # Crawl loop
            while state.repositories_processed < target_count:
                try:
                    # Fetch next batch
                    result = self.github.search_repositories(
                        query=search_query,
                        cursor=state.cursor,
                    )

                    # Store repositories in database
                    if result.repositories:
                        self.db.upsert_repositories(result.repositories)
                        state.repositories_processed += len(result.repositories)

                        logger.info(
                            f"Progress: {state.repositories_processed:,} / "
                            f"{target_count:,} repositories "
                            f"({state.repositories_processed / target_count * 100:.1f}%)"
                        )

                    # Update crawl state
                    state.cursor = result.cursor
                    state.last_update = datetime.now()
                    state.rate_limit_remaining = result.rate_limit_remaining
                    state.rate_limit_reset_at = result.rate_limit_reset_at

                    # Save state for resumption
                    self.db.save_crawl_state(state)

                    # Check if we've reached the end
                    if not result.has_next_page:
                        logger.info("Reached end of search results")
                        break

                    # Check if we've hit target
                    if state.repositories_processed >= target_count:
                        logger.info(f"Reached target of {target_count:,} repositories")
                        break

                except Exception as e:
                    logger.error(f"Error during crawl: {e}", exc_info=True)
                    # Save state before re-raising
                    self.db.save_crawl_state(state)
                    raise

        except KeyboardInterrupt:
            logger.info("Crawl interrupted by user")
            self.db.save_crawl_state(state)
            raise

        except Exception as e:
            logger.error(f"Crawl failed: {e}", exc_info=True)
            self.db.save_crawl_state(state)
            raise

        # Final state save
        self.db.save_crawl_state(state)

        logger.info(
            f"Crawl completed. Total repositories processed: "
            f"{state.repositories_processed:,}"
        )

        return state


class GetRepositoryStatistics:
    """
    Use case for retrieving repository statistics from the database.
    """

    def __init__(self, db_client: DatabaseClient):
        """
        Initialize the use case.

        Args:
            db_client: Database client
        """
        self.db = db_client

    def execute(self) -> dict:
        """
        Get repository statistics.

        Returns:
            Dictionary with statistics
        """
        total_repos = self.db.get_repository_count()
        top_repos = self.db.get_top_repositories(limit=10)

        stats = {
            "total_repositories": total_repos,
            "top_10_by_stars": [
                {
                    "name": f"{repo.owner}/{repo.name}",
                    "stars": repo.stars,
                    "forks": repo.forks,
                    "open_issues": repo.open_issues,
                }
                for repo in top_repos
            ],
        }

        return stats


class ExportRepositoryData:
    """
    Use case for exporting repository data.
    """

    def __init__(self, db_client: DatabaseClient):
        """
        Initialize the use case.

        Args:
            db_client: Database client
        """
        self.db = db_client

    def execute(self, output_path: str = "stars.csv"):
        """
        Export repository data to CSV.

        Args:
            output_path: Path to output file
        """
        logger.info(f"Exporting data to {output_path}")
        self.db.export_to_csv(output_path)
        logger.info("Export completed")
