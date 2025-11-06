#!/usr/bin/env python3
"""
Database setup script for GitStarCrawler.
Creates the PostgreSQL schema and initializes tables.
"""

import logging
import sys

from infrastructure.db_client import DatabaseClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def main():
    """Initialize database schema."""
    try:
        logger.info("Starting database setup...")

        # Create database client
        db = DatabaseClient()

        # Connect and create schema
        with db:
            db.create_schema()

        logger.info("Database setup completed successfully!")
        return 0

    except Exception as e:
        logger.error(f"Database setup failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
