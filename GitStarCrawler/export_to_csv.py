#!/usr/bin/env python3
"""
Export script for GitStarCrawler.
Exports repository data from PostgreSQL to CSV format.
"""

import logging
import sys
import argparse

from infrastructure.db_client import DatabaseClient
from core.use_cases import ExportRepositoryData

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def main():
    """Main export entry point."""
    parser = argparse.ArgumentParser(
        description="Export repository data to CSV"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="stars.csv",
        help="Output CSV file path (default: stars.csv)",
    )

    args = parser.parse_args()

    try:
        logger.info("=" * 60)
        logger.info("GitStarCrawler - Data Export")
        logger.info("=" * 60)
        logger.info(f"Output file: {args.output}")
        logger.info("=" * 60)

        # Initialize database client
        db = DatabaseClient()

        # Export data
        with db:
            # Get count first
            count = db.get_repository_count()
            logger.info(f"Exporting {count:,} repositories...")

            use_case = ExportRepositoryData(db)
            use_case.execute(args.output)

        logger.info("=" * 60)
        logger.info(f"Export completed successfully!")
        logger.info(f"Data saved to: {args.output}")
        logger.info("=" * 60)

        return 0

    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
