#!/usr/bin/env python3
"""
GitStarCrawler Demo Script
Demonstrates the crawler functionality with a small dataset using SQLite for easy testing.
"""

import logging
import sqlite3
from datetime import datetime
from typing import List, Optional
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Simple SQLite-based demo (no PostgreSQL required)
class DemoDatabase:
    """Lightweight SQLite database for demo purposes."""

    def __init__(self, db_path: str = "demo_github_data.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.create_schema()

    def create_schema(self):
        """Create demo database schema."""
        cursor = self.conn.cursor()

        # Create repositories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS repositories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_id INTEGER UNIQUE NOT NULL,
                name TEXT NOT NULL,
                owner TEXT NOT NULL,
                stars INTEGER NOT NULL,
                forks INTEGER,
                open_issues INTEGER,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create crawl state table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crawl_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cursor TEXT,
                repositories_processed INTEGER DEFAULT 0,
                last_update TEXT DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        """)

        self.conn.commit()
        logger.info("✓ Demo database schema created")

    def insert_sample_data(self):
        """Insert sample repository data."""
        cursor = self.conn.cursor()

        sample_repos = [
            (1, "linux", "torvalds", 180000, 52000, 450),
            (2, "Python", "python", 65000, 28000, 1500),
            (3, "vscode", "microsoft", 160000, 29000, 8500),
            (4, "react", "facebook", 225000, 46000, 1200),
            (5, "tensorflow", "tensorflow", 185000, 88000, 2100),
            (6, "kubernetes", "kubernetes", 110000, 40000, 900),
            (7, "vue", "vuejs", 207000, 33000, 650),
            (8, "awesome-python", "vinta", 200000, 25000, 120),
            (9, "free-programming-books", "EbookFoundation", 320000, 58000, 200),
            (10, "coding-interview-university", "jwasham", 300000, 75000, 80),
            (11, "developer-roadmap", "kamranahmedse", 280000, 38000, 150),
            (12, "public-apis", "public-apis", 290000, 33000, 300),
            (13, "node", "nodejs", 105000, 28000, 1800),
            (14, "deno", "denoland", 94000, 5200, 450),
            (15, "rust", "rust-lang", 95000, 12000, 9500),
            (16, "go", "golang", 120000, 17000, 8800),
            (17, "TypeScript", "microsoft", 98000, 12000, 6200),
            (18, "swift", "apple", 66000, 10000, 750),
            (19, "flutter", "flutter", 163000, 26000, 12500),
            (20, "django", "django", 77000, 31000, 200),
        ]

        for repo_id, name, owner, stars, forks, issues in sample_repos:
            cursor.execute(
                """
                INSERT OR REPLACE INTO repositories
                    (repo_id, name, owner, stars, forks, open_issues, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (repo_id, name, owner, stars, forks, issues, datetime.now().isoformat()),
            )

        self.conn.commit()
        logger.info(f"✓ Inserted {len(sample_repos)} sample repositories")

    def get_stats(self):
        """Get database statistics."""
        cursor = self.conn.cursor()

        # Total count
        cursor.execute("SELECT COUNT(*) FROM repositories")
        total = cursor.fetchone()[0]

        # Top 5 by stars
        cursor.execute("""
            SELECT name, owner, stars, forks, open_issues
            FROM repositories
            ORDER BY stars DESC
            LIMIT 5
        """)
        top_repos = cursor.fetchall()

        # Average stars
        cursor.execute("SELECT AVG(stars) FROM repositories")
        avg_stars = cursor.fetchone()[0]

        return {
            "total": total,
            "top_repos": top_repos,
            "avg_stars": avg_stars,
        }

    def export_csv(self, filename: str = "demo_stars.csv"):
        """Export data to CSV."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT repo_id, name, owner, stars, forks, open_issues, last_updated
            FROM repositories
            ORDER BY stars DESC
        """)

        with open(filename, "w", encoding="utf-8") as f:
            # Write header
            f.write("repo_id,name,owner,stars,forks,open_issues,last_updated\n")

            # Write rows
            for row in cursor.fetchall():
                f.write(",".join(map(str, row)) + "\n")

        logger.info(f"✓ Exported data to {filename}")
        return filename

    def close(self):
        """Close database connection."""
        self.conn.close()


def print_separator(char="=", length=70):
    """Print a separator line."""
    print(char * length)


def print_header(text: str):
    """Print a formatted header."""
    print_separator()
    print(f" {text}")
    print_separator()


def demo_github_api_simulation():
    """Simulate GitHub API interaction."""
    print_header("GitHub API Simulation")

    print("\n📡 Simulating GitHub GraphQL API request...\n")

    # Simulate GraphQL query
    query = """
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
              owner { login }
              stargazerCount
              forkCount
              issues(states: OPEN) { totalCount }
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

    print("GraphQL Query:")
    print("-" * 70)
    print(query)
    print("-" * 70)

    print("\n✓ API request successful!")
    print("✓ Rate limit: 4,950 / 5,000 remaining")
    print("✓ Fetched 20 repositories\n")


def demo_database_operations():
    """Demonstrate database operations."""
    print_header("Database Operations Demo")

    # Create database
    print("\n1. Creating SQLite database...")
    db = DemoDatabase("demo_github_data.db")

    # Insert sample data
    print("\n2. Inserting sample repository data...")
    db.insert_sample_data()

    # Get statistics
    print("\n3. Retrieving statistics...")
    stats = db.get_stats()

    print(f"\n📊 Database Statistics:")
    print(f"   Total repositories: {stats['total']}")
    print(f"   Average stars: {stats['avg_stars']:,.0f}")

    print(f"\n⭐ Top 5 Repositories by Stars:")
    print("-" * 70)
    for i, (name, owner, stars, forks, issues) in enumerate(stats['top_repos'], 1):
        print(f"   {i}. {owner}/{name}")
        print(f"      Stars: {stars:,} | Forks: {forks:,} | Open Issues: {issues:,}")

    return db


def demo_data_export(db: DemoDatabase):
    """Demonstrate data export."""
    print_header("Data Export Demo")

    print("\n📤 Exporting data to CSV...\n")
    filename = db.export_csv()

    # Show CSV preview
    print(f"Preview of {filename}:")
    print("-" * 70)
    with open(filename, "r", encoding="utf-8") as f:
        lines = f.readlines()[:6]  # Header + first 5 rows
        for line in lines:
            print(line.rstrip())
    print("-" * 70)
    print(f"\n✓ Full export saved to: {filename}")


def demo_clean_architecture():
    """Demonstrate clean architecture principles."""
    print_header("Clean Architecture Demo")

    print("""
The GitStarCrawler follows Clean Architecture principles:

┌─────────────────────────────────────────────────────────────────┐
│                        INTERFACE LAYER                          │
│  (crawl_stars.py, export_to_csv.py, CLI arguments)            │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                       USE CASES LAYER                           │
│  (CrawlRepositories, ExportRepositoryData, GetStatistics)      │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                       DOMAIN LAYER                              │
│  (Repository, CrawlState, CrawlResult entities)                │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                    INFRASTRUCTURE LAYER                         │
│  (GitHubClient, DatabaseClient, RateLimiter)                   │
└─────────────────────────────────────────────────────────────────┘

Benefits:
  ✓ Testable: Mock infrastructure in tests
  ✓ Flexible: Swap databases or APIs without changing business logic
  ✓ Maintainable: Clear boundaries between components
  ✓ Scalable: Easy to add new features or scale components
""")


def demo_rate_limiting():
    """Demonstrate rate limiting logic."""
    print_header("Rate Limiting Demo")

    print("""
GitStarCrawler implements smart rate limiting:

1. Monitor API Response Headers
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   X-RateLimit-Remaining: 4,950
   X-RateLimit-Reset: 2025-01-06T15:00:00Z

2. Proactive Waiting
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   When remaining < 100: Wait until reset time
   Prevents hitting hard limits

3. Exponential Backoff
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Retry 1: Wait 2 seconds
   Retry 2: Wait 4 seconds
   Retry 3: Wait 8 seconds
   Retry 4: Wait 16 seconds
   Retry 5: Wait 32 seconds

4. State Persistence
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Save cursor position after each batch
   Resume from exact point on failure
""")


def demo_scaling_strategy():
    """Demonstrate scaling strategy."""
    print_header("Scaling Strategy (100K → 500M)")

    print("""
Current Architecture (100K repos):
  • Single crawler instance
  • Single PostgreSQL database
  • 1 GitHub token (5,000 points/hour)
  • Performance: ~5,000 repos/hour
  • Time to 100K: ~20 hours

Target Architecture (500M repos):
  • 100+ distributed workers (Celery + Redis)
  • 10+ sharded PostgreSQL instances
  • 10 GitHub tokens (50,000 points/hour)
  • S3 for raw data archival
  • Async/await for concurrent requests
  • Performance: ~50,000 repos/hour (with optimization)
  • Time to 500M: ~42 days
  • Monthly cost: ~$23,000 (AWS)

Key Scaling Techniques:
  ✓ Task queue distribution (Kafka/Celery)
  ✓ Database sharding by repo_id
  ✓ Multiple token rotation
  ✓ GraphQL query batching
  ✓ Connection pooling (PgBouncer)
  ✓ Data partitioning (hot/warm/cold)
  ✓ Prometheus + Grafana monitoring

See SCALING.md for complete details!
""")


def main():
    """Run the complete demo."""
    print("\n")
    print("=" * 70)
    print(" " * 18 + "🌟 GitStarCrawler Demo 🌟")
    print("=" * 70)
    print("\nA production-ready system for crawling 100,000+ GitHub repositories")
    print("\n")

    try:
        # Demo 1: GitHub API Simulation
        demo_github_api_simulation()
        input("\nPress Enter to continue...")

        # Demo 2: Clean Architecture
        demo_clean_architecture()
        input("\nPress Enter to continue...")

        # Demo 3: Database Operations
        db = demo_database_operations()
        input("\nPress Enter to continue...")

        # Demo 4: Data Export
        demo_data_export(db)
        input("\nPress Enter to continue...")

        # Demo 5: Rate Limiting
        demo_rate_limiting()
        input("\nPress Enter to continue...")

        # Demo 6: Scaling Strategy
        demo_scaling_strategy()

        # Cleanup
        db.close()

        # Final summary
        print_header("Demo Complete!")
        print("""
✅ What was demonstrated:
   • GitHub GraphQL API integration pattern
   • Clean architecture implementation
   • Database operations (CREATE, INSERT, SELECT)
   • Data export to CSV
   • Rate limiting strategy
   • Scaling plan (100K → 500M repos)

📁 Demo artifacts created:
   • demo_github_data.db (SQLite database)
   • demo_stars.csv (Exported data)

🚀 Next steps:
   1. Set your GITHUB_TOKEN environment variable
   2. Run: python db_setup.py (for PostgreSQL)
   3. Run: python crawl_stars.py --target 1000
   4. Run: python export_to_csv.py

📖 Documentation:
   • README.md - Setup and usage guide
   • SCALING.md - Scaling to 500M repositories
   • PROJECT_SUMMARY.md - Project overview

Thank you for watching the demo! 🎉
""")

    except KeyboardInterrupt:
        print("\n\nDemo interrupted. Cleaning up...")
    except Exception as e:
        logger.error(f"Demo error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
