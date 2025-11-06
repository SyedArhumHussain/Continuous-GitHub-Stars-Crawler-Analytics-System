# Scaling GitStarCrawler to 500 Million Repositories

This document outlines the strategy for scaling GitStarCrawler from 100,000 to 500 million repositories.

## Current Architecture (100K Repos)

- **Single crawler instance**: One Python process
- **Single PostgreSQL database**: One instance
- **GitHub API**: 5,000 points/hour with one token
- **Performance**: ~5,000 repos/hour
- **Time to 100K**: ~20 hours

## Target Architecture (500M Repos)

### 1. Distributed Crawling System

#### Task Queue Architecture

```
┌─────────────┐         ┌─────────────┐
│   Task      │────────▶│   Workers   │
│   Queue     │         │   (100+)    │
│  (Kafka)    │         └─────────────┘
└─────────────┘                │
      ▲                        │
      │                        ▼
      │                ┌─────────────┐
      │                │  Database   │
      └────────────────│   Cluster   │
                       └─────────────┘
```

**Implementation:**

```python
# Using Celery with Redis
from celery import Celery

app = Celery('gitstarcrawler', broker='redis://localhost:6379')

@app.task(bind=True, max_retries=3)
def crawl_repo_batch(self, cursor, batch_size=100):
    """Crawl a batch of repositories."""
    try:
        github = GitHubClient()
        result = github.search_repositories(cursor=cursor)

        # Store in database
        db = DatabaseClient()
        db.upsert_repositories(result.repositories)

        # Queue next batch if available
        if result.has_next_page:
            crawl_repo_batch.delay(result.cursor, batch_size)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
```

**Benefits:**
- Horizontal scaling: Add workers as needed
- Fault tolerance: Failed tasks automatically retry
- Load balancing: Distribute work across workers
- Monitoring: Track progress in real-time

#### Partitioning Strategy

Partition repositories by ID ranges:

```
Worker 1: repo_id 0 - 10M
Worker 2: repo_id 10M - 20M
Worker 3: repo_id 20M - 30M
...
```

### 2. API Rate Limit Optimization

#### Multiple GitHub Tokens

Rotate between multiple tokens to increase throughput:

```python
class TokenPool:
    def __init__(self, tokens: List[str]):
        self.tokens = tokens
        self.current_index = 0
        self.rate_limits = {}

    def get_available_token(self) -> str:
        """Get a token with available rate limit."""
        for _ in range(len(self.tokens)):
            token = self.tokens[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.tokens)

            # Check if token has available rate limit
            if self.rate_limits.get(token, 5000) > 100:
                return token

        # All tokens exhausted, wait for reset
        self._wait_for_reset()
        return self.tokens[0]
```

**Calculation:**
- 10 tokens × 5,000 points/hour = 50,000 points/hour
- 100 repos/request × 500 requests/hour = 50,000 repos/hour
- 500M repos ÷ 50,000 repos/hour = 10,000 hours = 417 days

With optimization: **~42 days** (with caching and batching)

#### GraphQL Query Optimization

Batch multiple operations in a single query:

```graphql
query BatchSearch {
  search1: search(query: "stars:1000..2000", type: REPOSITORY, first: 100) {
    ...RepoFields
  }
  search2: search(query: "stars:2000..3000", type: REPOSITORY, first: 100) {
    ...RepoFields
  }
  # ... up to GitHub's query complexity limit
}
```

### 3. Database Scaling

#### Option A: PostgreSQL Partitioning

Partition the `repositories` table by ranges:

```sql
-- Create partitioned table
CREATE TABLE repositories (
  id SERIAL,
  repo_id BIGINT NOT NULL,
  name TEXT NOT NULL,
  owner TEXT NOT NULL,
  stars INTEGER NOT NULL,
  forks INTEGER,
  open_issues INTEGER,
  last_updated TIMESTAMP DEFAULT NOW()
) PARTITION BY RANGE (repo_id);

-- Create partitions
CREATE TABLE repositories_0_10m PARTITION OF repositories
  FOR VALUES FROM (0) TO (10000000);

CREATE TABLE repositories_10m_20m PARTITION OF repositories
  FOR VALUES FROM (10000000) TO (20000000);

-- ... continue for all ranges
```

**Benefits:**
- Query performance: Queries only scan relevant partitions
- Maintenance: Archive old partitions independently
- Scalability: Add partitions as data grows

#### Option B: Sharding Across Multiple Databases

Distribute data across multiple PostgreSQL instances:

```
Shard 1 (DB1): repo_id % 10 == 0
Shard 2 (DB2): repo_id % 10 == 1
Shard 3 (DB3): repo_id % 10 == 2
...
Shard 10 (DB10): repo_id % 10 == 9
```

```python
class ShardedDatabaseClient:
    def __init__(self, shard_configs: List[dict]):
        self.shards = [
            DatabaseClient(**config) for config in shard_configs
        ]

    def get_shard(self, repo_id: int) -> DatabaseClient:
        """Get the shard for a given repo_id."""
        shard_index = repo_id % len(self.shards)
        return self.shards[shard_index]

    def upsert_repositories(self, repositories: List[Repository]):
        """Upsert repositories to appropriate shards."""
        # Group by shard
        shard_repos = {}
        for repo in repositories:
            shard = self.get_shard(repo.repo_id)
            shard_repos.setdefault(shard, []).append(repo)

        # Insert to each shard
        for shard, repos in shard_repos.items():
            shard.upsert_repositories(repos)
```

#### Option C: Cloud Data Warehouse

For analytics workloads, use a cloud data warehouse:

**BigQuery:**
```sql
-- Daily ETL from PostgreSQL to BigQuery
CREATE OR REPLACE TABLE `project.dataset.repositories`
PARTITION BY DATE(last_updated)
CLUSTER BY stars DESC
AS
SELECT * FROM EXTERNAL_QUERY(
  'projects/PROJECT/locations/LOCATION/connections/CONNECTION',
  'SELECT * FROM repositories WHERE last_updated >= CURRENT_DATE - 1'
);
```

**Snowflake:**
```sql
-- Continuous data ingestion from S3
CREATE PIPE repositories_pipe
AS
COPY INTO repositories
FROM @s3_stage/repositories/
FILE_FORMAT = (TYPE = PARQUET);
```

### 4. Data Storage Strategy

#### Tiered Storage

```
Hot Data (Recent 7 days):
  └─ PostgreSQL (fast queries)

Warm Data (7-90 days):
  └─ Compressed PostgreSQL or Parquet on S3

Cold Data (90+ days):
  └─ S3 Glacier (archival)
```

#### Object Storage for Raw Data

Store raw GitHub API responses in S3:

```python
import boto3
import json

class S3RawStorage:
    def __init__(self):
        self.s3 = boto3.client('s3')
        self.bucket = 'gitstarcrawler-raw-data'

    def store_raw_response(self, response: dict, cursor: str):
        """Store raw API response in S3."""
        key = f"raw/{datetime.now().strftime('%Y/%m/%d')}/{cursor}.json"
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(response),
            StorageClass='INTELLIGENT_TIERING'
        )
```

### 5. Schema Evolution for Additional Metadata

#### Pull Requests Table

```sql
CREATE TABLE pull_requests (
  id SERIAL PRIMARY KEY,
  repo_id BIGINT REFERENCES repositories(repo_id),
  pr_id BIGINT UNIQUE NOT NULL,
  pr_number INTEGER NOT NULL,
  title TEXT,
  author TEXT,
  status TEXT,  -- open, closed, merged
  comment_count INTEGER,
  review_count INTEGER,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  merged_at TIMESTAMP,
  last_synced TIMESTAMP DEFAULT NOW()
) PARTITION BY RANGE (repo_id);

CREATE INDEX idx_pr_repo ON pull_requests(repo_id);
CREATE INDEX idx_pr_updated ON pull_requests(updated_at);
```

#### PR Comments Table

```sql
CREATE TABLE pr_comments (
  id SERIAL PRIMARY KEY,
  pr_id BIGINT REFERENCES pull_requests(pr_id),
  comment_id BIGINT UNIQUE NOT NULL,
  author TEXT,
  body TEXT,
  created_at TIMESTAMP,
  last_synced TIMESTAMP DEFAULT NOW()
) PARTITION BY RANGE (pr_id);
```

#### Incremental Sync Strategy

Only fetch updated data:

```graphql
query FetchUpdatedPRs($repoOwner: String!, $repoName: String!, $since: DateTime!) {
  repository(owner: $repoOwner, name: $repoName) {
    pullRequests(first: 100, orderBy: {field: UPDATED_AT, direction: DESC}) {
      edges {
        node {
          id
          number
          title
          updatedAt
          comments(first: 100) {
            edges {
              node {
                id
                author { login }
                body
                createdAt
              }
            }
          }
        }
      }
    }
  }
}
```

```python
def incremental_sync_prs(repo_id: int, last_sync: datetime):
    """Sync only PRs updated since last sync."""
    # Fetch updated PRs from GitHub
    prs = fetch_prs_since(repo_id, last_sync)

    # Upsert to database
    db.upsert_pull_requests(prs)

    # Update sync timestamp
    db.update_sync_timestamp(repo_id, datetime.now())
```

### 6. Performance Optimizations

#### Async/Await for Concurrent Requests

```python
import asyncio
import aiohttp

class AsyncGitHubClient:
    async def fetch_batch(self, cursors: List[str]) -> List[CrawlResult]:
        """Fetch multiple batches concurrently."""
        async with aiohttp.ClientSession() as session:
            tasks = [
                self._fetch_page(session, cursor)
                for cursor in cursors
            ]
            return await asyncio.gather(*tasks)

    async def _fetch_page(self, session, cursor):
        """Fetch a single page asynchronously."""
        async with session.post(
            self.GRAPHQL_ENDPOINT,
            json={"query": self.SEARCH_QUERY, "variables": {"cursor": cursor}},
            headers=self.headers
        ) as response:
            return await response.json()
```

#### Connection Pooling

```python
# PgBouncer configuration
[databases]
github_data = host=localhost dbname=github_data

[pgbouncer]
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
```

#### Bulk Copy for Massive Inserts

```python
import io

def bulk_copy_repositories(repositories: List[Repository]):
    """Use COPY for maximum insert performance."""
    # Create CSV buffer
    buffer = io.StringIO()
    for repo in repositories:
        buffer.write(f"{repo.repo_id},{repo.name},{repo.owner},"
                    f"{repo.stars},{repo.forks},{repo.open_issues}\n")

    buffer.seek(0)

    # Use COPY command
    cursor.copy_expert(
        "COPY repositories (repo_id, name, owner, stars, forks, open_issues) "
        "FROM STDIN WITH CSV",
        buffer
    )
```

### 7. Monitoring & Observability

#### Metrics to Track

```python
from prometheus_client import Counter, Histogram, Gauge

# Counters
repos_crawled = Counter('repos_crawled_total', 'Total repositories crawled')
api_requests = Counter('github_api_requests_total', 'Total API requests')
api_errors = Counter('github_api_errors_total', 'Total API errors')

# Histograms
request_duration = Histogram('github_api_duration_seconds', 'API request duration')
batch_size = Histogram('crawl_batch_size', 'Repositories per batch')

# Gauges
rate_limit_remaining = Gauge('github_rate_limit_remaining', 'Remaining API calls')
active_workers = Gauge('crawler_active_workers', 'Active crawler workers')
```

#### Grafana Dashboard

Key metrics to visualize:
- Repositories crawled per hour
- API rate limit usage
- Database write throughput
- Worker health and distribution
- Error rates and types
- Queue depth

### 8. Cost Estimation (500M Repos)

#### Infrastructure Costs (AWS)

```
EC2 Instances (workers):
  - 20 × c5.2xlarge (8 vCPU, 16GB RAM) = $3,400/month

RDS PostgreSQL (sharded):
  - 10 × db.r5.4xlarge (16 vCPU, 128GB RAM) = $18,000/month

ElastiCache Redis (queue):
  - cache.r5.xlarge = $300/month

S3 Storage (raw data):
  - 10TB × $0.023/GB = $230/month

Data Transfer:
  - Estimate $1,000/month

Total: ~$23,000/month
```

#### GitHub API Costs

```
GitHub Enterprise Cloud:
  - 10 seats with API access = $210/month

Total Infrastructure: ~$23,210/month
```

### 9. Timeline Estimate

**Phase 1 (Months 1-2): Infrastructure Setup**
- Set up Kafka/Celery task queue
- Implement worker orchestration
- Database sharding/partitioning
- Monitoring and alerting

**Phase 2 (Months 3-4): Initial Crawl**
- Crawl first 100M repositories
- Optimize based on bottlenecks
- Tune database performance
- Refine worker scaling

**Phase 3 (Months 5-6): Scale to 500M**
- Complete crawl of 500M repositories
- Implement incremental sync
- Archive old data to cold storage
- Optimize costs

**Phase 4 (Ongoing): Maintenance**
- Daily incremental updates
- Monitor and optimize costs
- Add new metadata types
- Scale as needed

## Recommended Approach

For 500M repositories, I recommend:

1. **Use cloud-native services** (AWS/GCP/Azure) for elasticity
2. **Implement task queue** (Celery + Redis) for distributed crawling
3. **Shard PostgreSQL** across 10+ instances
4. **Use S3 for raw data** archival and long-term storage
5. **Async workers** with 10+ GitHub tokens
6. **Incremental sync** after initial crawl
7. **Comprehensive monitoring** with Prometheus + Grafana

This architecture can handle 500M repositories in approximately **6 months** with a monthly cost of ~$23,000.
