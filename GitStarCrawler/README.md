# GitStarCrawler

A scalable, production-ready system for continuously collecting and storing metadata from 100,000+ GitHub repositories using the GitHub GraphQL API and PostgreSQL.

## Features

- **GitHub GraphQL API Integration**: Efficient data fetching with pagination
- **Rate Limiting**: Smart handling of GitHub API rate limits with exponential backoff
- **Resumable Crawls**: Automatic checkpoint saving and resumption
- **Clean Architecture**: Separation of concerns with domain entities, use cases, and infrastructure
- **PostgreSQL Storage**: Optimized schema with UPSERT for incremental updates
- **CI/CD Pipeline**: GitHub Actions workflow with automated testing and data export
- **Scalable Design**: Architecture ready to scale to millions of repositories

## Architecture

```
gitstarcrawler/
│
├── core/                      # Business logic (domain layer)
│   ├── entities.py           # Domain models (Repository, CrawlState, etc.)
│   └── use_cases.py          # Business use cases (CrawlRepositories, etc.)
│
├── infrastructure/            # External dependencies layer
│   ├── github_client.py      # GitHub GraphQL API wrapper
│   ├── db_client.py          # PostgreSQL connection + queries
│   └── retry_utils.py        # Rate limit handling and retries
│
├── interface/                 # Interface layer (planned)
│   ├── cli.py                # CLI entrypoint
│   └── scheduler.py          # Cron or GitHub Actions runner
│
├── tests/                     # Test suite
│   ├── test_crawler.py
│   └── test_db.py
│
├── .github/
│   └── workflows/
│       └── main.yml          # CI/CD pipeline
│
├── crawl_stars.py            # Main crawler script
├── db_setup.py               # Database initialization
├── export_to_csv.py          # Data export utility
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL 14+
- GitHub Personal Access Token

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/GitStarCrawler.git
cd GitStarCrawler
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Copy the example environment file and add your GitHub token:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
GITHUB_TOKEN=your_github_personal_access_token
DB_HOST=localhost
DB_PORT=5432
DB_NAME=github_data
DB_USER=github
DB_PASSWORD=github
```

### 4. Set Up Database

Start PostgreSQL and create the schema:

```bash
# Start PostgreSQL (example for Docker)
docker run --name postgres-gitstarcrawler \
  -e POSTGRES_USER=github \
  -e POSTGRES_PASSWORD=github \
  -e POSTGRES_DB=github_data \
  -p 5432:5432 \
  -d postgres:14

# Initialize schema
python db_setup.py
```

### 5. Run the Crawler

```bash
# Crawl 100,000 repositories
python crawl_stars.py --target 100000 --stats

# Or start with a smaller target for testing
python crawl_stars.py --target 1000 --stats
```

### 6. Export Data

```bash
python export_to_csv.py --output stars.csv
```

## Usage

### Crawl Repositories

```bash
# Basic usage (100k repos)
python crawl_stars.py

# Custom target
python crawl_stars.py --target 50000

# Custom search query
python crawl_stars.py --query "stars:>100 language:python"

# Start fresh (don't resume)
python crawl_stars.py --no-resume

# Show statistics after crawl
python crawl_stars.py --stats
```

### Resume Interrupted Crawls

The crawler automatically saves progress. If interrupted, simply run it again:

```bash
python crawl_stars.py
# Automatically resumes from last checkpoint
```

### Export Data

```bash
# Export to CSV
python export_to_csv.py --output my_data.csv

# The CSV includes: repo_id, name, owner, stars, forks, open_issues, last_updated
```

## Database Schema

### repositories

Stores core repository metadata:

```sql
CREATE TABLE repositories (
  id SERIAL PRIMARY KEY,
  repo_id BIGINT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  owner TEXT NOT NULL,
  stars INTEGER NOT NULL,
  forks INTEGER,
  open_issues INTEGER,
  last_updated TIMESTAMP DEFAULT NOW(),
  created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for efficient queries
CREATE INDEX idx_repo_id ON repositories(repo_id);
CREATE INDEX idx_owner_name ON repositories(owner, name);
CREATE INDEX idx_stars ON repositories(stars DESC);
```

### crawl_state

Tracks crawl progress for resumption:

```sql
CREATE TABLE crawl_state (
  id SERIAL PRIMARY KEY,
  cursor TEXT,
  repositories_processed INTEGER DEFAULT 0,
  last_update TIMESTAMP DEFAULT NOW(),
  rate_limit_remaining INTEGER,
  rate_limit_reset_at TIMESTAMP,
  is_active BOOLEAN DEFAULT TRUE
);
```

## GitHub Actions CI/CD

The project includes a complete CI/CD pipeline at [.github/workflows/main.yml](.github/workflows/main.yml).

### Pipeline Features

- **Automated crawling** on push, PR, or schedule (daily at 2 AM UTC)
- **PostgreSQL service container** for testing
- **Data export** to CSV artifacts
- **Artifact upload** with 30-day retention
- **Release automation** on tagged commits

### Triggering the Pipeline

```bash
# Push to main branch
git push origin main

# Manual trigger via GitHub UI
# Go to Actions → GitStarCrawler Pipeline → Run workflow

# Schedule (runs daily at 2 AM UTC automatically)
```

### Accessing Results

1. Go to **Actions** tab in GitHub
2. Click on latest workflow run
3. Download **github-stars-data** artifact
4. Extract `stars.csv`

## Rate Limiting

The crawler respects GitHub's API rate limits:

- **GraphQL API**: 5,000 points/hour for authenticated requests
- **Smart backoff**: Automatically waits when approaching limits
- **Exponential retry**: Handles transient errors with backoff
- **Progress saving**: Never loses work on interruption

### Rate Limit Strategy

```python
# The crawler monitors rate limits in real-time
# When remaining < 100 requests, it waits until reset
# Each query is automatically retried with exponential backoff
```

## Scaling to 500 Million Repositories

For scaling beyond 100k repositories, consider:

### 1. Distributed Crawling

- **Task Queue**: Use Celery with Redis/RabbitMQ for distributed workers
- **Horizontal Scaling**: Run multiple crawler instances with partition keys
- **Orchestration**: Kubernetes for auto-scaling workers

### 2. Data Storage

- **Partitioning**: Partition `repositories` table by `repo_id` ranges
- **Sharding**: Distribute data across multiple PostgreSQL instances
- **Cloud Data Warehouse**: Migrate to BigQuery, Snowflake, or Redshift
- **Object Storage**: Store raw JSON in S3 for long-term archival

### 3. API Optimization

- **Multiple Tokens**: Rotate between multiple GitHub tokens
- **GraphQL Batching**: Fetch multiple repos in single query (GitHub supports 100/query)
- **Caching**: Redis cache for frequently accessed data
- **CDC Pipeline**: Use Change Data Capture for incremental syncs

### 4. Schema Evolution

For additional metadata (issues, PRs, commits, comments):

```sql
-- Pull Requests
CREATE TABLE pull_requests (
  id SERIAL PRIMARY KEY,
  repo_id BIGINT REFERENCES repositories(repo_id),
  pr_id BIGINT UNIQUE,
  title TEXT,
  status TEXT,
  comment_count INTEGER,
  created_at TIMESTAMP,
  last_updated TIMESTAMP
);

-- PR Comments
CREATE TABLE pr_comments (
  id SERIAL PRIMARY KEY,
  pr_id BIGINT REFERENCES pull_requests(pr_id),
  comment_id BIGINT UNIQUE,
  author TEXT,
  body TEXT,
  created_at TIMESTAMP
);

-- Issues
CREATE TABLE issues (
  id SERIAL PRIMARY KEY,
  repo_id BIGINT REFERENCES repositories(repo_id),
  issue_id BIGINT UNIQUE,
  title TEXT,
  status TEXT,
  comment_count INTEGER,
  created_at TIMESTAMP,
  last_updated TIMESTAMP
);

-- Use updated_at timestamps for incremental sync
-- Only fetch/update rows where last_updated > our_last_sync
```

### 5. Performance Optimizations

```python
# Async I/O with aiohttp
import asyncio
import aiohttp

async def crawl_async():
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_repo(session, repo_id) for repo_id in repo_ids]
        await asyncio.gather(*tasks)

# Bulk inserts (already implemented)
# COPY command for massive imports
# Connection pooling with pgbouncer
```

### 6. Monitoring & Observability

- **Metrics**: Prometheus + Grafana for crawler metrics
- **Logging**: Structured logging with ELK stack
- **Alerting**: PagerDuty for rate limit exhaustion, failures
- **Dashboards**: Track repos/hour, API usage, error rates

## Performance Benchmarks

On a standard machine with 5000 API points/hour:

- **Fetch rate**: ~5,000 repos/hour (100 repos/request × 50 requests/hour)
- **100k repos**: ~20 hours
- **500M repos**: ~10,000 hours (~417 days with single token)

With 10 tokens and distributed workers:

- **500M repos**: ~42 days

## Development

### Running Tests

```bash
pytest tests/
```

### Code Structure

The project follows **Clean Architecture** principles:

1. **Domain Layer** (`core/`): Business entities and use cases
2. **Infrastructure Layer** (`infrastructure/`): External dependencies
3. **Interface Layer** (`interface/`, scripts): User-facing interfaces

This separation ensures:
- **Testability**: Mock infrastructure in tests
- **Flexibility**: Swap databases or APIs without changing business logic
- **Maintainability**: Clear boundaries between components

## Troubleshooting

### Database Connection Issues

```bash
# Check if PostgreSQL is running
pg_isready -h localhost -p 5432

# Verify credentials
psql -h localhost -p 5432 -U github -d github_data
```

### GitHub API Rate Limit

```bash
# Check your current rate limit
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://api.github.com/rate_limit
```

### Resume Not Working

```bash
# Check crawl state in database
psql -h localhost -U github -d github_data \
  -c "SELECT * FROM crawl_state WHERE is_active = TRUE;"

# Reset state if needed
psql -h localhost -U github -d github_data \
  -c "UPDATE crawl_state SET is_active = FALSE;"
```

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License - See [LICENSE](LICENSE) file for details.

## Acknowledgments

- GitHub GraphQL API: https://docs.github.com/en/graphql
- PostgreSQL: https://www.postgresql.org/
- Clean Architecture: Robert C. Martin

## Contact

For questions or support, please open an issue on GitHub.

---

**Happy Crawling!** ⭐
