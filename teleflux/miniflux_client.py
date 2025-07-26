"""Miniflux API client module.

This module provides a comprehensive client for interacting with the Miniflux RSS reader API.
It handles authentication, feed management, category operations, and includes robust error
handling with detailed error reporting.

The client supports both basic authentication and API token authentication, with API tokens
being the preferred method for security and performance. It includes automatic URL validation,
feed discovery, and intelligent conflict resolution for existing feeds.

Key features:
    - Category management (create, list, get by ID)
    - Feed management (create, update, delete, validate)
    - Intelligent feed conflict resolution
    - Comprehensive error handling and logging
    - Feed URL validation with custom headers
    - Category-based feed organization
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from .config import MinifluxConfig

logger = logging.getLogger(__name__)


@dataclass
class MinifluxCategory:
    """Miniflux category representation.

    Attributes:
        id: Unique category identifier
        title: Human-readable category name
    """

    id: int
    title: str


@dataclass
class MinifluxFeed:
    """Miniflux feed representation.

    Attributes:
        id: Unique feed identifier
        title: Human-readable feed title
        feed_url: RSS/Atom feed URL
        category_id: ID of the category this feed belongs to
    """

    id: int
    title: str
    feed_url: str
    category_id: int


class MinifluxClient:
    """Miniflux API client for RSS reader operations.

    Provides methods for managing categories and feeds in Miniflux RSS reader.
    Supports authentication via API token and includes comprehensive error handling.
    """

    def __init__(self, config: MinifluxConfig):
        """Initialize Miniflux API client.

        Args:
            config: Miniflux configuration containing API credentials and server URL
        """
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Auth-Token": config.token,
                "Content-Type": "application/json",
                "User-Agent": "Teleflux",
            }
        )

    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make HTTP request to Miniflux API with error handling.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path (will be prefixed with /v1)
            **kwargs: Additional parameters for requests

        Returns:
            Server response object

        Raises:
            requests.RequestException: On request error with detailed error information
        """
        url = f"{self.config.url}/v1{endpoint}"

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            # Try to get more detailed error information from response
            error_details = str(e)
            if hasattr(e, "response") and e.response is not None:
                try:
                    # Try to get JSON error details from API response
                    error_json = e.response.json()
                    if "error_message" in error_json:
                        error_details = f"{e} - {error_json['error_message']}"
                    elif "message" in error_json:
                        error_details = f"{e} - {error_json['message']}"
                    else:
                        error_details = f"{e} - Response: {error_json}"
                except (ValueError, KeyError):
                    # If not JSON, try to get text content
                    try:
                        response_text = e.response.text[
                            :500
                        ]  # Limit to first 500 chars to avoid log spam
                        if response_text:
                            error_details = f"{e} - Response: {response_text}"
                    except:
                        pass  # Use original error message

            logger.error(f"Miniflux API request error {method} {url}: {error_details}")
            raise

    def get_categories(self) -> list[MinifluxCategory]:
        """Get list of all categories from Miniflux.

        Returns:
            List of all categories available in the Miniflux instance
        """
        logger.debug("Getting categories list")
        response = self._make_request("GET", "/categories")

        categories = []
        for cat_data in response.json():
            categories.append(
                MinifluxCategory(id=cat_data["id"], title=cat_data["title"])
            )

        logger.debug(f"Got {len(categories)} categories")
        return categories

    def create_category(self, title: str) -> MinifluxCategory:
        """Create new category in Miniflux.

        Args:
            title: Category name

        Returns:
            Newly created category object
        """
        logger.debug(f"Creating category: {title}")
        response = self._make_request("POST", "/categories", json={"title": title})

        cat_data = response.json()
        category = MinifluxCategory(id=cat_data["id"], title=cat_data["title"])

        logger.info(f"Category created: {title}")
        return category

    def get_feeds(self) -> list[MinifluxFeed]:
        """Get list of all feeds from Miniflux.

        Returns:
            List of all feeds available in the Miniflux instance
        """
        logger.debug("Getting feeds list")
        response = self._make_request("GET", "/feeds")

        feeds = []
        for feed_data in response.json():
            feeds.append(
                MinifluxFeed(
                    id=feed_data["id"],
                    title=feed_data["title"],
                    feed_url=feed_data["feed_url"],
                    category_id=feed_data["category"]["id"],
                )
            )

        logger.debug(f"Got {len(feeds)} feeds")
        return feeds

    def validate_feed_url(self, feed_url: str) -> bool:
        """Validate that a feed URL is accessible and responds correctly.

        Performs a HEAD request to check if the feed URL is reachable.
        Uses custom User-Agent to avoid bot blocking.

        Args:
            feed_url: Feed URL to validate

        Returns:
            True if feed is accessible and returns 200 OK, False otherwise
        """
        try:
            logger.debug(f"Validating feed URL: {feed_url}")
            headers = {"User-Agent": "Teleflux"}
            response = requests.head(
                feed_url, timeout=10, allow_redirects=True, headers=headers
            )

            if response.status_code == 200:
                logger.debug(f"Feed URL validation successful: {feed_url}")
                return True
            else:
                logger.warning(
                    f"Feed URL returned status {response.status_code}: {feed_url}"
                )
                return False

        except requests.RequestException as e:
            logger.warning(f"Feed URL validation failed for {feed_url}: {e}")
            return False

    def create_feed(
        self,
        feed_url: str,
        category_id: int,
        validate: bool = True,
        title: str | None = None,
    ) -> MinifluxFeed:
        """Create new feed in Miniflux with intelligent conflict resolution.

        This method handles the complexity of feed creation including:
        - Optional URL validation before creation
        - Handling existing feeds (moving to correct category if needed)
        - Custom title setting after creation
        - Comprehensive error handling and logging

        Args:
            feed_url: RSS/Atom feed URL
            category_id: Target category ID for the feed
            validate: If True, validate feed URL accessibility before creation
            title: Custom title for the feed (optional, will update after creation)

        Returns:
            Created or existing feed object

        Raises:
            ValueError: If feed URL validation fails or feed creation fails
        """
        logger.debug(f"Creating feed: {feed_url}")

        # Validate feed URL if requested
        if validate and not self.validate_feed_url(feed_url):
            raise ValueError(f"Feed URL is not accessible: {feed_url}")

        try:
            response = self._make_request(
                "POST",
                "/feeds",
                json={"feed_url": feed_url, "category_id": category_id},
            )

            feed_data = response.json()

            # The create feed API returns only feed_id, so we need to fetch the full feed details
            feed_id = feed_data["feed_id"]

            # Get the full feed details
            feed_response = self._make_request("GET", f"/feeds/{feed_id}")
            full_feed_data = feed_response.json()

            feed = MinifluxFeed(
                id=full_feed_data["id"],
                title=full_feed_data["title"],
                feed_url=full_feed_data["feed_url"],
                category_id=full_feed_data["category"]["id"],
            )

            # Set custom title if provided and different from auto-detected title
            if title and title != feed.title:
                logger.debug(f"Updating existing feed title to: '{title}'")
                self.update_feed(feed.id, title, log_level="debug")
                feed.title = title

            logger.info(f"Feed created: {feed.title}")
            return feed

        except requests.RequestException as e:
            # Check if this is a 400 Bad Request error (often means feed already exists)
            if (
                hasattr(e, "response")
                and e.response is not None
                and e.response.status_code == 400
            ):
                try:
                    error_json = e.response.json()
                    error_message = error_json.get("error_message", "")

                    if "already exists" in error_message.lower():
                        # Feed already exists - find it and move to correct category if needed
                        logger.info(
                            f"Feed already exists, checking category: {feed_url}"
                        )
                        existing_feeds = self.get_feeds()
                        for feed in existing_feeds:
                            if feed.feed_url == feed_url:
                                category_moved = False
                                if feed.category_id != category_id:
                                    # Get category name for better logging
                                    category = self.get_category_by_id(category_id)
                                    category_name = (
                                        category.title
                                        if category
                                        else f"category {category_id}"
                                    )
                                    logger.debug(
                                        f"Moving existing feed '{feed.title}' to category '{category_name}'"
                                    )
                                    self.update_feed_category(feed.id, category_id)
                                    # Update the feed object with new category
                                    feed.category_id = category_id
                                    category_moved = True

                                # Update title if provided and different
                                if title and title != feed.title:
                                    logger.debug(
                                        f"Updating existing feed title to: '{title}'"
                                    )
                                    self.update_feed(feed.id, title, log_level="debug")
                                    feed.title = title
                                elif not category_moved:
                                    # Only log "already in correct category" if we didn't just move it
                                    category = self.get_category_by_id(feed.category_id)
                                    category_name = (
                                        category.title
                                        if category
                                        else f"category {feed.category_id}"
                                    )
                                    logger.info(
                                        f"Feed '{feed.title}' already in correct category '{category_name}'"
                                    )

                                return feed

                        # If we can't find the existing feed, raise a more specific error
                        raise ValueError(
                            f"Feed already exists but could not be found: {feed_url}"
                        )
                    else:
                        # Other 400 errors - pass through the actual error message
                        raise ValueError(
                            f"Bad request when creating feed: {error_message}"
                        )

                except (ValueError, KeyError):
                    # If we can't parse the JSON response, try to get text content
                    try:
                        error_text = e.response.text
                        raise ValueError(
                            f"Bad request when creating feed: {error_text}"
                        )
                    except:
                        # Fall back to original exception
                        raise ValueError(f"Bad request when creating feed: {str(e)}")
            else:
                # Re-raise for non-400 errors
                raise

    def delete_feed(self, feed_id: int) -> None:
        """Delete feed from Miniflux.

        Args:
            feed_id: Unique identifier of the feed to delete
        """
        # Get feed title for better logging before deletion
        try:
            feed_response = self._make_request("GET", f"/feeds/{feed_id}")
            feed_data = feed_response.json()
            feed_title = feed_data["title"]

            self._make_request("DELETE", f"/feeds/{feed_id}")
            logger.info(f"Feed deleted: {feed_title}")
        except Exception:
            # If we can't get the feed title, just delete without logging the title
            self._make_request("DELETE", f"/feeds/{feed_id}")
            logger.info("Feed deleted")

    def update_feed(self, feed_id: int, title: str, log_level: str = "info") -> None:
        """Update feed title in Miniflux.

        Args:
            feed_id: Unique identifier of the feed to update
            title: New feed title
            log_level: Log level for the update message ('info' or 'debug')
        """
        logger.debug(f"Updating feed title to: {title}")
        self._make_request("PUT", f"/feeds/{feed_id}", json={"title": title})

        # Log at the specified level for flexible logging control
        if log_level.lower() == "debug":
            logger.debug(f"Feed title updated to: {title}")
        else:
            logger.info(f"Feed title updated to: {title}")

    def get_category_by_id(self, category_id: int) -> MinifluxCategory | None:
        """Get category by its unique identifier.

        Args:
            category_id: Unique category identifier

        Returns:
            Category object if found, None if not found
        """
        categories = self.get_categories()
        for category in categories:
            if category.id == category_id:
                return category
        return None

    def update_feed_category(self, feed_id: int, category_id: int) -> None:
        """Move feed to a different category.

        Args:
            feed_id: Unique identifier of the feed to move
            category_id: Target category ID
        """
        # Get feed and category names for better logging
        feed_response = self._make_request("GET", f"/feeds/{feed_id}")
        feed_data = feed_response.json()
        feed_title = feed_data["title"]

        category = self.get_category_by_id(category_id)
        category_name = category.title if category else f"category {category_id}"

        self._make_request(
            "PUT", f"/feeds/{feed_id}", json={"category_id": category_id}
        )
        logger.info(f"Feed '{feed_title}' moved to category '{category_name}'")

    def get_or_create_category(self, title: str) -> MinifluxCategory:
        """Get existing category or create new one if it doesn't exist.

        This method provides idempotent category creation, ensuring that
        categories are not duplicated when the same name is requested multiple times.

        Args:
            title: Category name

        Returns:
            Existing or newly created category object
        """
        # Search for existing category
        categories = self.get_categories()
        for category in categories:
            if category.title == title:
                logger.debug(f"Found existing category: {title}")
                return category

        # Create new category if not found
        return self.create_category(title)

    def get_feeds_by_category(self, category_id: int) -> list[MinifluxFeed]:
        """Get all feeds belonging to a specific category.

        Args:
            category_id: Unique category identifier

        Returns:
            List of feeds in the specified category
        """
        all_feeds = self.get_feeds()
        return [feed for feed in all_feeds if feed.category_id == category_id]
