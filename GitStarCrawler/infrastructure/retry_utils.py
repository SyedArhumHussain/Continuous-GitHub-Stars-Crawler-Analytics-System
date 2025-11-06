"""
Retry utilities with exponential backoff for handling rate limits and transient errors.
"""

import time
import logging
from typing import Callable, TypeVar, Any
from functools import wraps
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RateLimitExceeded(Exception):
    """Raised when GitHub API rate limit is exceeded."""
    def __init__(self, reset_at: datetime):
        self.reset_at = reset_at
        super().__init__(f"Rate limit exceeded. Resets at {reset_at}")


def exponential_backoff(
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0
) -> Callable:
    """
    Decorator for exponential backoff retry logic.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        exponential_base: Multiplier for exponential growth
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except RateLimitExceeded as e:
                    # For rate limits, wait until reset time
                    wait_time = (e.reset_at - datetime.now()).total_seconds()
                    if wait_time > 0:
                        logger.warning(
                            f"Rate limit exceeded. Waiting {wait_time:.1f}s until reset"
                        )
                        time.sleep(wait_time + 1)  # Add 1s buffer
                    continue
                except Exception as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"Max retries ({max_retries}) reached for {func.__name__}"
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay
                    )

                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries} failed for "
                        f"{func.__name__}: {str(e)}. Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception

            return func(*args, **kwargs)

        return wrapper
    return decorator


class RateLimiter:
    """
    Rate limiter to ensure we don't exceed GitHub API limits.
    Tracks requests and enforces delays when approaching limits.
    """

    def __init__(self, max_requests: int = 5000, time_window: int = 3600):
        """
        Args:
            max_requests: Maximum requests allowed in the time window
            time_window: Time window in seconds (default 1 hour)
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests_made = 0
        self.window_start = datetime.now()
        self.last_reset_at: datetime | None = None

    def wait_if_needed(self, remaining: int | None = None):
        """
        Wait if necessary to avoid hitting rate limits.

        Args:
            remaining: Remaining requests from API response headers
        """
        if remaining is not None and remaining < 100:
            if self.last_reset_at:
                wait_time = (self.last_reset_at - datetime.now()).total_seconds()
                if wait_time > 0:
                    logger.warning(
                        f"Approaching rate limit ({remaining} remaining). "
                        f"Waiting {wait_time:.1f}s"
                    )
                    time.sleep(wait_time + 1)
                    self.requests_made = 0
                    self.window_start = datetime.now()

    def update_from_headers(self, remaining: int, reset_at: datetime):
        """
        Update rate limiter state from API response headers.

        Args:
            remaining: Remaining requests
            reset_at: When the rate limit resets
        """
        self.last_reset_at = reset_at

        # If we're low on requests, be more conservative
        if remaining < 500:
            logger.info(f"Rate limit status: {remaining} requests remaining")

    def record_request(self):
        """Record that a request was made."""
        now = datetime.now()

        # Reset counter if we're in a new time window
        if (now - self.window_start).total_seconds() > self.time_window:
            self.requests_made = 0
            self.window_start = now

        self.requests_made += 1

        # Add small delay between requests to be respectful
        if self.requests_made > 0 and self.requests_made % 100 == 0:
            time.sleep(0.5)
