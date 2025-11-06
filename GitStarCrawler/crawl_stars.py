#!/usr/bin/env python3
"""
Main crawler script for GitStarCrawler.
Fetches repository metadata from GitHub and stores in PostgreSQL.
"""

import logging
import sys
import argparse

from infrastructure.github_client import GitHubClient
from infrastructure.db_client import DatabaseClient
from core.use_cases import CrawlRepositories, GetRepositoryStatistics

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def main():
    """Main crawler entry point."""
    parser = argparse.ArgumentParser(
        description="Crawl GitHub repositories and store metadata"
    )
    parser.add_argument(
        "--target",
        type=int,
        default=100000,
        help="Target number of repositories to crawl (default: 100000)",
    )
    parser.add_argument(
        "--query",
        type=str,
        default="stars:>1",
        help="GitHub search query (default: 'stars:>1')",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Start fresh instead of resuming previous crawl",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=100,
        help="Repositories per page (max 100, default: 100)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Display statistics after crawl",
    )

    args = parser.parse_args()

    try:
        logger.info("=" * 60)
        logger.info("GitStarCrawler - GitHub Repository Metadata Crawler")
        logger.info("=" * 60)
        logger.info(f"Target repositories: {args.target:,}")
        logger.info(f"Search query: {args.query}")
        logger.info(f"Resume mode: {not args.no_resume}")
        logger.info("=" * 60)

        # Initialize clients
        logger.info("Initializing GitHub client...")
        github = GitHubClient(per_page=args.per_page)

        logger.info("Initializing database client...")
        db = DatabaseClient()

        # Execute crawl
        with db:
            logger.info("Starting crawl...")
            use_case = CrawlRepositories(github, db)

            state = use_case.execute(
                target_count=args.target,
                search_query=args.query,
                resume=not args.no_resume,
            )

            logger.info("=" * 60)
            logger.info("Crawl Summary:")
            logger.info(f"  Repositories processed: {state.repositories_processed:,}")
            logger.info(f"  Last cursor: {state.cursor[:30] if state.cursor else 'N/A'}...")
            logger.info(f"  Rate limit remaining: {state.rate_limit_remaining}")
            logger.info("=" * 60)

            # Display statistics if requested
            if args.stats:
                logger.info("Fetching statistics...")
                stats_use_case = GetRepositoryStatistics(db)
                stats = stats_use_case.execute()

                logger.info("=" * 60)
                logger.info("Repository Statistics:")
                logger.info(f"  Total repositories in DB: {stats['total_repositories']:,}")
                logger.info("")
                logger.info("  Top 10 repositories by stars:")
                for i, repo in enumerate(stats['top_10_by_stars'], 1):
                    logger.info(
                        f"    {i:2d}. {repo['name']:40s} "
                        f"{repo['stars']:8,} stars, "
                        f"{repo['forks']:6,} forks"
                    )
                logger.info("=" * 60)

        logger.info("Crawl completed successfully!")
        return 0

    except KeyboardInterrupt:
        logger.info("\nCrawl interrupted by user. Progress has been saved.")
        return 130  # Standard exit code for SIGINT

    except Exception as e:
        logger.error(f"Crawl failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
