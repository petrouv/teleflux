"""
Tests for miniflux_client module
"""

from unittest.mock import Mock, patch

import pytest
import requests

from teleflux.miniflux_client import (
    MinifluxClient,
    MinifluxConfig,
    MinifluxFeed,
)


@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    return MinifluxConfig(url="http://localhost:8080", token="test_token")


@pytest.fixture
def client(mock_config):
    """Create MinifluxClient instance for testing"""
    return MinifluxClient(mock_config)


def test_create_feed_success(client):
    """Test successful feed creation with correct API response format"""

    # Mock the API responses
    create_response = Mock()
    create_response.json.return_value = {"feed_id": 123}

    get_response = Mock()
    get_response.json.return_value = {
        "id": 123,
        "title": "Test Feed",
        "feed_url": "http://example.com/feed.xml",
        "category": {"id": 1},
    }

    with patch.object(client, "_make_request") as mock_request:
        # Configure the mock to return different responses for different calls
        mock_request.side_effect = [create_response, get_response]

        # Mock the validate_feed_url method to return True
        with patch.object(client, "validate_feed_url", return_value=True):
            # Call create_feed
            feed = client.create_feed("http://example.com/feed.xml", 1)

            # Verify the result
            assert isinstance(feed, MinifluxFeed)
            assert feed.id == 123
            assert feed.title == "Test Feed"
            assert feed.feed_url == "http://example.com/feed.xml"
            assert feed.category_id == 1

            # Verify the correct API calls were made
            assert mock_request.call_count == 2

            # First call should be POST to create feed
            first_call = mock_request.call_args_list[0]
            assert first_call[0][0] == "POST"  # method
            assert first_call[0][1] == "/feeds"  # endpoint
            assert first_call[1]["json"] == {
                "feed_url": "http://example.com/feed.xml",
                "category_id": 1,
            }

            # Second call should be GET to fetch feed details
            second_call = mock_request.call_args_list[1]
            assert second_call[0][0] == "GET"  # method
            assert second_call[0][1] == "/feeds/123"  # endpoint


def test_create_feed_validation_disabled(client):
    """Test feed creation with validation disabled"""

    create_response = Mock()
    create_response.json.return_value = {"feed_id": 456}

    get_response = Mock()
    get_response.json.return_value = {
        "id": 456,
        "title": "Test Feed No Validation",
        "feed_url": "http://example.com/feed2.xml",
        "category": {"id": 2},
    }

    with patch.object(client, "_make_request") as mock_request:
        mock_request.side_effect = [create_response, get_response]

        # Mock validate_feed_url to return False (but it shouldn't be called)
        with patch.object(
            client, "validate_feed_url", return_value=False
        ) as mock_validate:
            # Call create_feed with validation disabled
            feed = client.create_feed("http://example.com/feed2.xml", 2, validate=False)

            # Verify the result
            assert feed.id == 456
            assert feed.title == "Test Feed No Validation"

            # Verify validation was not called
            mock_validate.assert_not_called()


def test_create_feed_validation_fails(client):
    """Test feed creation when URL validation fails"""

    with patch.object(client, "validate_feed_url", return_value=False):
        # Should raise ValueError when validation fails
        with pytest.raises(ValueError, match="Feed URL is not accessible"):
            client.create_feed("http://invalid-url.com/feed.xml", 1)


def test_create_feed_already_exists(client):
    """Test feed creation when feed already exists"""

    # Mock the create request to return 400 error (feed exists)
    error_response = Mock()
    error_response.status_code = 400
    error_response.json.return_value = {"error_message": "This feed already exists"}

    error = requests.HTTPError("400 Client Error")
    error.response = error_response

    # Mock existing feeds
    existing_feed = MinifluxFeed(
        id=789,
        title="Existing Feed",
        feed_url="http://example.com/existing.xml",
        category_id=1,
    )

    # Mock categories response for get_category_by_id call
    categories_response = Mock()
    categories_response.json.return_value = [{"id": 1, "title": "Test Category"}]

    with patch.object(client, "_make_request") as mock_request:
        # First call (create feed) returns error, second call (get categories) succeeds
        mock_request.side_effect = [error, categories_response]

        with patch.object(client, "validate_feed_url", return_value=True):
            with patch.object(client, "get_feeds", return_value=[existing_feed]):
                # Should return the existing feed
                feed = client.create_feed("http://example.com/existing.xml", 1)

                assert feed.id == 789
                assert feed.title == "Existing Feed"


def test_create_feed_api_error(client):
    """Test feed creation when API returns an error"""

    # Mock the create request to return 500 error
    error = requests.HTTPError("500 Server Error")

    with patch.object(client, "_make_request") as mock_request:
        mock_request.side_effect = error

        with patch.object(client, "validate_feed_url", return_value=True):
            # Should re-raise the error
            with pytest.raises(requests.HTTPError):
                client.create_feed("http://example.com/feed.xml", 1)


def test_create_feed_missing_feed_id_in_response(client):
    """Test feed creation when API response is missing feed_id"""

    # Mock response without feed_id (should cause KeyError)
    create_response = Mock()
    create_response.json.return_value = {"id": 123}  # Wrong field name

    with patch.object(client, "_make_request", return_value=create_response):
        with patch.object(client, "validate_feed_url", return_value=True):
            # Should raise KeyError for missing feed_id
            with pytest.raises(KeyError, match="feed_id"):
                client.create_feed("http://example.com/feed.xml", 1)


def test_get_categories(client):
    """Test getting categories"""

    response = Mock()
    response.json.return_value = [
        {"id": 1, "title": "News"},
        {"id": 2, "title": "Tech"},
    ]

    with patch.object(client, "_make_request", return_value=response):
        categories = client.get_categories()

        assert len(categories) == 2
        assert categories[0].id == 1
        assert categories[0].title == "News"
        assert categories[1].id == 2
        assert categories[1].title == "Tech"


def test_create_category(client):
    """Test creating a category"""

    response = Mock()
    response.json.return_value = {"id": 3, "title": "New Category"}

    with patch.object(client, "_make_request", return_value=response):
        category = client.create_category("New Category")

        assert category.id == 3
        assert category.title == "New Category"


def test_get_feeds(client):
    """Test getting feeds"""

    response = Mock()
    response.json.return_value = [
        {
            "id": 1,
            "title": "Feed 1",
            "feed_url": "http://example.com/feed1.xml",
            "category": {"id": 1},
        },
        {
            "id": 2,
            "title": "Feed 2",
            "feed_url": "http://example.com/feed2.xml",
            "category": {"id": 2},
        },
    ]

    with patch.object(client, "_make_request", return_value=response):
        feeds = client.get_feeds()

        assert len(feeds) == 2
        assert feeds[0].id == 1
        assert feeds[0].title == "Feed 1"
        assert feeds[0].feed_url == "http://example.com/feed1.xml"
        assert feeds[0].category_id == 1
        assert feeds[1].id == 2
        assert feeds[1].title == "Feed 2"
        assert feeds[1].feed_url == "http://example.com/feed2.xml"
        assert feeds[1].category_id == 2


def test_create_feed_with_custom_title(client):
    """Test feed creation with custom title"""

    # Mock the API responses
    create_response = Mock()
    create_response.json.return_value = {"feed_id": 123}

    get_response = Mock()
    get_response.json.return_value = {
        "id": 123,
        "title": "Original Feed Title",
        "feed_url": "http://example.com/feed.xml",
        "category": {"id": 1},
    }

    update_response = Mock()

    with patch.object(client, "_make_request") as mock_request:
        # Configure the mock to return different responses for different calls
        mock_request.side_effect = [create_response, get_response, update_response]

        # Mock the validate_feed_url method to return True
        with patch.object(client, "validate_feed_url", return_value=True):
            # Call create_feed with custom title
            feed = client.create_feed(
                "http://example.com/feed.xml", 1, title="Custom Channel Title"
            )

            # Verify the result
            assert isinstance(feed, MinifluxFeed)
            assert feed.id == 123
            assert (
                feed.title == "Custom Channel Title"
            )  # Should be updated to custom title
            assert feed.feed_url == "http://example.com/feed.xml"
            assert feed.category_id == 1

            # Verify the correct API calls were made
            assert mock_request.call_count == 3

            # First call should be POST to create feed
            first_call = mock_request.call_args_list[0]
            assert first_call[0][0] == "POST"  # method
            assert first_call[0][1] == "/feeds"  # endpoint
            assert first_call[1]["json"] == {
                "feed_url": "http://example.com/feed.xml",
                "category_id": 1,
            }

            # Second call should be GET to fetch feed details
            second_call = mock_request.call_args_list[1]
            assert second_call[0][0] == "GET"  # method
            assert second_call[0][1] == "/feeds/123"  # endpoint

            # Third call should be PUT to update feed title
            third_call = mock_request.call_args_list[2]
            assert third_call[0][0] == "PUT"  # method
            assert third_call[0][1] == "/feeds/123"  # endpoint
            assert third_call[1]["json"] == {"title": "Custom Channel Title"}


def test_create_feed_with_same_title(client):
    """Test feed creation with custom title that matches original title"""

    # Mock the API responses
    create_response = Mock()
    create_response.json.return_value = {"feed_id": 123}

    get_response = Mock()
    get_response.json.return_value = {
        "id": 123,
        "title": "Same Title",
        "feed_url": "http://example.com/feed.xml",
        "category": {"id": 1},
    }

    with patch.object(client, "_make_request") as mock_request:
        # Configure the mock to return different responses for different calls
        mock_request.side_effect = [create_response, get_response]

        # Mock the validate_feed_url method to return True
        with patch.object(client, "validate_feed_url", return_value=True):
            # Call create_feed with title that matches original
            feed = client.create_feed(
                "http://example.com/feed.xml", 1, title="Same Title"
            )

            # Verify the result
            assert isinstance(feed, MinifluxFeed)
            assert feed.id == 123
            assert feed.title == "Same Title"
            assert feed.feed_url == "http://example.com/feed.xml"
            assert feed.category_id == 1

            # Verify only 2 API calls were made (no update needed)
            assert mock_request.call_count == 2


def test_create_feed_already_exists_with_title_update(client):
    """Test feed creation when feed already exists and title needs update"""

    # Mock the create request to return 400 error (feed exists)
    error_response = Mock()
    error_response.status_code = 400
    error_response.json.return_value = {"error_message": "This feed already exists"}

    error = requests.HTTPError("400 Client Error")
    error.response = error_response

    # Mock existing feeds
    existing_feed = MinifluxFeed(
        id=789,
        title="Old Title",
        feed_url="http://example.com/existing.xml",
        category_id=1,
    )

    update_response = Mock()

    with patch.object(client, "_make_request") as mock_request:
        mock_request.side_effect = [error, update_response]

        with patch.object(client, "validate_feed_url", return_value=True):
            with patch.object(client, "get_feeds", return_value=[existing_feed]):
                # Should return the existing feed with updated title
                feed = client.create_feed(
                    "http://example.com/existing.xml", 1, title="New Title"
                )

                assert feed.id == 789
                assert feed.title == "New Title"  # Should be updated

                # Verify update call was made
                assert mock_request.call_count == 2
                update_call = mock_request.call_args_list[1]
                assert update_call[0][0] == "PUT"  # method
                assert update_call[0][1] == "/feeds/789"  # endpoint
                assert update_call[1]["json"] == {"title": "New Title"}
