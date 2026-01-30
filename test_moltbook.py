"""Tests for Moltbook CLI."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from moltbook import cli, format_time, handle_error


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_api_key():
    with patch("moltbook.get_api_key", return_value="test_api_key"):
        yield


# Sample API responses
SAMPLE_POST = {
    "id": "abc123",
    "title": "Test Post",
    "content": "This is test content",
    "url": "/post/abc123",
    "upvotes": 10,
    "downvotes": 2,
    "comment_count": 5,
    "created_at": "2026-01-30T12:00:00+00:00",
    "author": {"id": "user1", "username": "testuser", "name": "Test User", "karma": 42},
    "submolt": {"name": "general"},
}

SAMPLE_COMMENT = {
    "id": "comment1",
    "content": "Test comment",
    "parent_id": None,
    "upvotes": 3,
    "downvotes": 0,
    "created_at": "2026-01-30T13:00:00+00:00",
    "author": {"id": "user2", "name": "Commenter", "karma": 10},
    "replies": [],
}


class TestFormatTime:
    def test_returns_unknown_for_none(self):
        assert format_time(None) == "unknown"

    def test_returns_unknown_for_empty(self):
        assert format_time("") == "unknown"

    def test_handles_invalid_format(self):
        assert format_time("not-a-date") == "not-a-date"


class TestFeedCommand:
    def test_feed_default(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"posts": [SAMPLE_POST]}

        with patch("requests.request", return_value=response) as mock_req:
            result = runner.invoke(cli, ["feed"])

            assert result.exit_code == 0
            assert "Test Post" in result.output
            assert "testuser" in result.output
            assert "abc123" in result.output

            mock_req.assert_called_once()
            call_args = mock_req.call_args
            assert call_args[1]["params"] == {"sort": "hot", "limit": 20}

    def test_feed_with_options(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"posts": [SAMPLE_POST]}

        with patch("requests.request", return_value=response) as mock_req:
            result = runner.invoke(cli, ["feed", "--sort", "new", "--limit", "5"])

            assert result.exit_code == 0
            call_args = mock_req.call_args
            assert call_args[1]["params"] == {"sort": "new", "limit": 5}

    def test_feed_json_output(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"posts": [SAMPLE_POST]}

        with patch("requests.request", return_value=response):
            result = runner.invoke(cli, ["feed", "--json"])

            assert result.exit_code == 0
            output = json.loads(result.output)
            assert "posts" in output
            assert output["posts"][0]["id"] == "abc123"

    def test_feed_empty(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"posts": []}

        with patch("requests.request", return_value=response):
            result = runner.invoke(cli, ["feed"])

            assert result.exit_code == 0
            assert "No posts found" in result.output


class TestPostCommand:
    def test_post_with_comments(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "post": SAMPLE_POST,
            "comments": [SAMPLE_COMMENT],
        }

        with patch("requests.request", return_value=response):
            result = runner.invoke(cli, ["post", "abc123"])

            assert result.exit_code == 0
            assert "Test Post" in result.output
            assert "This is test content" in result.output
            assert "Test comment" in result.output
            assert "Commenter" in result.output

    def test_post_no_comments(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"post": SAMPLE_POST, "comments": []}

        with patch("requests.request", return_value=response):
            result = runner.invoke(cli, ["post", "abc123"])

            assert result.exit_code == 0
            assert "No comments yet" in result.output

    def test_post_json_output(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"post": SAMPLE_POST, "comments": []}

        with patch("requests.request", return_value=response):
            result = runner.invoke(cli, ["post", "abc123", "--json"])

            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["post"]["id"] == "abc123"


class TestCreateCommand:
    def test_create_success(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "message": "Post created!",
            "post": {"id": "new123", "url": "/post/new123"},
        }

        with patch("requests.request", return_value=response) as mock_req:
            result = runner.invoke(
                cli, ["create", "--title", "New Post", "--content", "Content here"]
            )

            assert result.exit_code == 0
            assert "Post created!" in result.output
            assert "new123" in result.output

            call_args = mock_req.call_args
            assert call_args[1]["json"]["title"] == "New Post"
            assert call_args[1]["json"]["content"] == "Content here"
            assert call_args[1]["json"]["submolt"] == "general"

    def test_create_rate_limited(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "success": False,
            "error": "You can only post once every 30 minutes",
            "hint": "Wait 27 minutes before posting again",
            "retry_after_minutes": 27,
        }

        with patch("requests.request", return_value=response):
            result = runner.invoke(
                cli, ["create", "--title", "New Post", "--content", "Content"]
            )

            assert result.exit_code == 1
            assert "30 minutes" in result.output
            assert "27 minutes" in result.output

    def test_create_missing_fields(self, runner, mock_api_key):
        result = runner.invoke(cli, ["create", "--title", "Only Title"])

        assert result.exit_code == 2
        assert "Missing option" in result.output or "required" in result.output.lower()


class TestDeleteCommand:
    def test_delete_success(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"success": True, "message": "Post deleted"}

        with patch("requests.request", return_value=response) as mock_req:
            result = runner.invoke(cli, ["delete", "abc123"])

            assert result.exit_code == 0
            assert "Post deleted" in result.output

            call_args = mock_req.call_args
            assert call_args[0][0] == "DELETE"
            assert "/posts/abc123" in call_args[0][1]

    def test_delete_not_owner(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "success": False,
            "error": "You can only delete your own posts",
        }

        with patch("requests.request", return_value=response):
            result = runner.invoke(cli, ["delete", "abc123"])

            assert result.exit_code == 1
            assert "only delete your own" in result.output


class TestCommentCommand:
    def test_comment_success(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "message": "Comment added!",
            "comment": {"id": "comment123"},
        }

        with patch("requests.request", return_value=response) as mock_req:
            result = runner.invoke(
                cli, ["comment", "abc123", "--content", "Great post!"]
            )

            assert result.exit_code == 0
            assert "Comment added!" in result.output
            assert "comment123" in result.output

            call_args = mock_req.call_args
            assert call_args[1]["json"]["content"] == "Great post!"
            assert "parent_id" not in call_args[1]["json"]

    def test_comment_reply(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "message": "Comment added!",
            "comment": {"id": "reply123", "parent_id": "parent456"},
        }

        with patch("requests.request", return_value=response) as mock_req:
            result = runner.invoke(
                cli,
                [
                    "comment",
                    "abc123",
                    "--content",
                    "I agree",
                    "--reply-to",
                    "parent456",
                ],
            )

            assert result.exit_code == 0
            call_args = mock_req.call_args
            assert call_args[1]["json"]["parent_id"] == "parent456"


class TestUserCommand:
    def test_user_profile(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "user": {
                "id": "user1",
                "username": "testuser",
                "name": "Test User",
                "bio": "I am a test user",
                "karma": 42,
                "follower_count": 10,
                "following_count": 5,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        }

        with patch("requests.request", return_value=response):
            result = runner.invoke(cli, ["user", "testuser"])

            assert result.exit_code == 0
            assert "Test User" in result.output
            assert "@testuser" in result.output
            assert "42" in result.output
            assert "I am a test user" in result.output


class TestErrorHandling:
    def test_404_error(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 404

        with patch("requests.request", return_value=response):
            result = runner.invoke(cli, ["post", "nonexistent"])

            assert result.exit_code == 1
            assert "Not found" in result.output

    def test_401_error(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 401

        with patch("requests.request", return_value=response):
            result = runner.invoke(cli, ["feed"])

            assert result.exit_code == 1
            assert "Authentication failed" in result.output

    def test_connection_error(self, runner, mock_api_key):
        import requests as req

        with patch("requests.request", side_effect=req.exceptions.ConnectionError()):
            result = runner.invoke(cli, ["feed"])

            assert result.exit_code == 1
            assert "Could not connect" in result.output

    def test_timeout_error(self, runner, mock_api_key):
        import requests as req

        with patch("requests.request", side_effect=req.exceptions.Timeout()):
            result = runner.invoke(cli, ["feed"])

            assert result.exit_code == 1
            assert "timed out" in result.output


class TestAuthHeader:
    def test_bearer_token_sent(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"posts": []}

        with patch("requests.request", return_value=response) as mock_req:
            runner.invoke(cli, ["feed"])

            call_args = mock_req.call_args
            assert call_args[1]["headers"]["Authorization"] == "Bearer test_api_key"


class TestFeedSubmoltFilter:
    def test_feed_with_submolt(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"posts": [SAMPLE_POST]}

        with patch("requests.request", return_value=response) as mock_req:
            result = runner.invoke(cli, ["feed", "--submolt", "programming"])

            assert result.exit_code == 0
            call_args = mock_req.call_args
            assert call_args[1]["params"]["submolt"] == "programming"

    def test_feed_without_submolt(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"posts": []}

        with patch("requests.request", return_value=response) as mock_req:
            runner.invoke(cli, ["feed"])

            call_args = mock_req.call_args
            assert "submolt" not in call_args[1]["params"]


class TestSubmoltsCommand:
    def test_submolts_list(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "submolts": [
                {
                    "name": "general",
                    "display_name": "General",
                    "description": "Main community",
                    "member_count": 1000,
                },
                {
                    "name": "programming",
                    "display_name": "Programming",
                    "description": "Code talk",
                    "member_count": 500,
                },
            ]
        }

        with patch("requests.request", return_value=response):
            result = runner.invoke(cli, ["submolts"])

            assert result.exit_code == 0
            assert "General" in result.output
            assert "general" in result.output
            assert "Programming" in result.output
            assert "1000 members" in result.output

    def test_submolts_empty(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"submolts": []}

        with patch("requests.request", return_value=response):
            result = runner.invoke(cli, ["submolts"])

            assert result.exit_code == 0
            assert "No submolts found" in result.output

    def test_submolts_json(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"submolts": [{"name": "general"}]}

        with patch("requests.request", return_value=response):
            result = runner.invoke(cli, ["submolts", "--json"])

            assert result.exit_code == 0
            output = json.loads(result.output)
            assert "submolts" in output


class TestUpvoteCommand:
    def test_upvote_success(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"success": True, "message": "Upvoted!"}

        with patch("requests.request", return_value=response) as mock_req:
            result = runner.invoke(cli, ["upvote", "abc123"])

            assert result.exit_code == 0
            assert "Upvoted" in result.output

            call_args = mock_req.call_args
            assert call_args[0][0] == "POST"
            assert "/posts/abc123/upvote" in call_args[0][1]

    def test_upvote_already_voted(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "success": False,
            "error": "Already voted on this post",
        }

        with patch("requests.request", return_value=response):
            result = runner.invoke(cli, ["upvote", "abc123"])

            assert result.exit_code == 1
            assert "Already voted" in result.output


class TestDownvoteCommand:
    def test_downvote_success(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"success": True, "message": "Downvoted!"}

        with patch("requests.request", return_value=response) as mock_req:
            result = runner.invoke(cli, ["downvote", "abc123"])

            assert result.exit_code == 0
            assert "Downvoted" in result.output

            call_args = mock_req.call_args
            assert call_args[0][0] == "POST"
            assert "/posts/abc123/downvote" in call_args[0][1]


class TestUpvoteCommentCommand:
    def test_upvote_comment_success(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"success": True, "message": "Upvoted!"}

        with patch("requests.request", return_value=response) as mock_req:
            result = runner.invoke(cli, ["upvote-comment", "comment123"])

            assert result.exit_code == 0
            assert "Upvoted" in result.output

            call_args = mock_req.call_args
            assert call_args[0][0] == "POST"
            assert "/comments/comment123/upvote" in call_args[0][1]


class TestDownvoteCommentCommand:
    def test_downvote_comment_success(self, runner, mock_api_key):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"success": True, "message": "Downvoted!"}

        with patch("requests.request", return_value=response) as mock_req:
            result = runner.invoke(cli, ["downvote-comment", "comment123"])

            assert result.exit_code == 0
            assert "Downvoted" in result.output

            call_args = mock_req.call_args
            assert call_args[0][0] == "POST"
            assert "/comments/comment123/downvote" in call_args[0][1]
