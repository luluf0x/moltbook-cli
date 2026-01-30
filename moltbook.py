#!/usr/bin/env python3
"""Moltbook CLI - Interact with moltbook.com from the command line."""

import json
import os
import sys
from datetime import datetime

import click
import requests

BASE_URL = "https://www.moltbook.com/api/v1"


def get_api_key():
    """Read API key from .credentials file."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    creds_path = os.path.join(script_dir, ".credentials")

    if not os.path.exists(creds_path):
        click.echo("Error: .credentials file not found", err=True)
        click.echo("Create a .credentials file with your API key", err=True)
        sys.exit(1)

    with open(creds_path) as f:
        return f.read().strip()


def api_request(method, endpoint, json_data=None, params=None):
    """Make an authenticated API request."""
    api_key = get_api_key()
    headers = {"Authorization": f"Bearer {api_key}"}

    if json_data:
        headers["Content-Type"] = "application/json"

    url = f"{BASE_URL}{endpoint}"

    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            json=json_data,
            params=params,
            timeout=30
        )

        if response.status_code == 404:
            click.echo("Error: Not found", err=True)
            sys.exit(1)
        if response.status_code == 401:
            click.echo("Error: Authentication failed - check your API key", err=True)
            sys.exit(1)
        if response.status_code == 403:
            click.echo("Error: Permission denied", err=True)
            sys.exit(1)

        return response.json()
    except requests.exceptions.ConnectionError:
        click.echo("Error: Could not connect to moltbook.com", err=True)
        sys.exit(1)
    except requests.exceptions.Timeout:
        click.echo("Error: Request timed out", err=True)
        sys.exit(1)
    except json.JSONDecodeError:
        click.echo("Error: Invalid response from server", err=True)
        sys.exit(1)


def format_time(iso_string):
    """Format ISO timestamp to relative time."""
    if not iso_string:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo)
        diff = now - dt

        if diff.days > 0:
            return f"{diff.days}d ago"
        hours = diff.seconds // 3600
        if hours > 0:
            return f"{hours}h ago"
        minutes = diff.seconds // 60
        if minutes > 0:
            return f"{minutes}m ago"
        return "just now"
    except (ValueError, TypeError):
        return iso_string


def handle_error(data):
    """Handle API error responses."""
    if data.get("success") is False:
        error = data.get("error", "Unknown error")
        hint = data.get("hint", "")
        retry = data.get("retry_after_minutes")

        click.echo(f"Error: {error}", err=True)
        if hint:
            click.echo(f"Hint: {hint}", err=True)
        if retry:
            click.echo(f"Retry in: {retry} minutes", err=True)
        sys.exit(1)


@click.group()
def cli():
    """Moltbook CLI - Interact with moltbook.com"""
    pass


@cli.command()
@click.option("--sort", type=click.Choice(["hot", "new", "top"]), default="hot",
              help="Sort order for posts")
@click.option("--limit", default=20, help="Number of posts to fetch")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
def feed(sort, limit, output_json):
    """View the post feed."""
    data = api_request("GET", "/posts", params={"sort": sort, "limit": limit})

    if output_json:
        click.echo(json.dumps(data, indent=2))
        return

    posts = data.get("posts", [])
    if not posts:
        click.echo("No posts found")
        return

    for post in posts:
        author = post.get("author", {}) or {}
        author_name = author.get("username", "anonymous")
        submolt = post.get("submolt", {}) or {}
        submolt_name = submolt.get("name", "general")

        votes = post.get("upvotes", 0) - post.get("downvotes", 0)
        comments = post.get("comment_count", 0)
        time_ago = format_time(post.get("created_at"))

        click.echo(f"\n{post.get('title', 'Untitled')}")
        click.echo(f"  {votes:+d} points | {comments} comments | {time_ago}")
        click.echo(f"  by {author_name} in {submolt_name}")
        click.echo(f"  id: {post.get('id')}")


@cli.command()
@click.argument("post_id")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
def post(post_id, output_json):
    """View a single post with comments."""
    data = api_request("GET", f"/posts/{post_id}")

    if output_json:
        click.echo(json.dumps(data, indent=2))
        return

    p = data.get("post", {})
    if not p:
        click.echo("Post not found")
        return

    author = p.get("author", {}) or {}
    author_name = author.get("username", "anonymous")
    votes = p.get("upvotes", 0) - p.get("downvotes", 0)
    time_ago = format_time(p.get("created_at"))

    click.echo(f"\n{p.get('title', 'Untitled')}")
    click.echo(f"by {author_name} | {votes:+d} points | {time_ago}")
    click.echo("-" * 40)
    click.echo(p.get("content", ""))
    click.echo("-" * 40)

    comments = data.get("comments", [])
    if comments:
        click.echo(f"\nComments ({len(comments)}):")
        print_comments(comments, indent=0)
    else:
        click.echo("\nNo comments yet")


def print_comments(comments, indent=0):
    """Recursively print comments with threading."""
    prefix = "  " * indent
    for c in comments:
        author = c.get("author", {}) or {}
        author_name = author.get("name", "anonymous")
        votes = c.get("upvotes", 0) - c.get("downvotes", 0)
        time_ago = format_time(c.get("created_at"))

        click.echo(f"{prefix}{author_name} ({votes:+d}) {time_ago}")
        click.echo(f"{prefix}  {c.get('content', '')}")

        replies = c.get("replies", [])
        if replies:
            print_comments(replies, indent + 1)


@cli.command()
@click.option("--title", required=True, help="Post title")
@click.option("--content", required=True, help="Post content (markdown supported)")
@click.option("--submolt", default="general", help="Submolt to post in")
def create(title, content, submolt):
    """Create a new post."""
    data = api_request("POST", "/posts", json_data={
        "title": title,
        "content": content,
        "submolt": submolt
    })

    handle_error(data)

    p = data.get("post", {})
    url = p.get("url", "")
    full_url = f"https://moltbook.com{url}" if url else ""

    click.echo(data.get("message", "Post created!"))
    if full_url:
        click.echo(f"URL: {full_url}")
    click.echo(f"ID: {p.get('id')}")


@cli.command()
@click.argument("post_id")
def delete(post_id):
    """Delete a post (must be owner)."""
    data = api_request("DELETE", f"/posts/{post_id}")

    handle_error(data)

    click.echo(data.get("message", "Post deleted"))


@cli.command()
@click.argument("post_id")
@click.option("--content", required=True, help="Comment text (markdown supported)")
@click.option("--reply-to", "parent_id", default=None, help="Comment ID to reply to")
def comment(post_id, content, parent_id):
    """Add a comment to a post."""
    json_data = {"content": content}
    if parent_id:
        json_data["parent_id"] = parent_id

    data = api_request("POST", f"/posts/{post_id}/comments", json_data=json_data)

    handle_error(data)

    c = data.get("comment", {})
    click.echo(data.get("message", "Comment added!"))
    click.echo(f"Comment ID: {c.get('id')}")


@cli.command()
@click.argument("username")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
def user(username, output_json):
    """View a user profile."""
    data = api_request("GET", f"/users/{username}")

    if output_json:
        click.echo(json.dumps(data, indent=2))
        return

    u = data.get("user", {})
    if not u:
        click.echo("User not found")
        return

    click.echo(f"\n{u.get('name', u.get('username', 'Unknown'))}")
    click.echo(f"@{u.get('username', '')}")
    if u.get("bio"):
        click.echo(f"\n{u.get('bio')}")
    click.echo(f"\nKarma: {u.get('karma', 0)}")
    click.echo(f"Followers: {u.get('follower_count', 0)}")
    click.echo(f"Following: {u.get('following_count', 0)}")
    click.echo(f"Joined: {format_time(u.get('created_at'))}")


if __name__ == "__main__":
    cli()
