"""
Thin client around LeetCode's public (unofficial) GraphQL endpoint.

Two queries are used:
1. userProfileUserQuestionProgressV2 -> cumulative solved counts by difficulty (all-time totals)
2. recentAcSubmissionList -> recent accepted submissions, used to figure out if the user
   solved anything in the last 24h and to split today's solves by difficulty.

LeetCode does not expose a clean "solved today, by difficulty" field directly, so we derive
it: pull recent accepted submissions, filter to the ones timestamped today, then look up each
problem's difficulty via the same progress query's per-difficulty breakdown is NOT per-problem,
so for simplicity we tag difficulty using the problem list cache built from recent submissions'
titleSlug -> question detail lookup (batched, cached in-memory for the process lifetime).
"""

import time
import requests
from datetime import datetime, timezone

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

_difficulty_cache: dict[str, str] = {}


def _post(query: str, variables: dict) -> dict:
    resp = requests.post(
        LEETCODE_GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers={"Content-Type": "application/json", "Referer": "https://leetcode.com"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()

def validate_username(username: str) -> bool:
    """
    Returns True if the LeetCode username exists, False otherwise.

    LeetCode's GraphQL does NOT return null or an HTTP error for a nonexistent username -
    it returns HTTP 200 with an empty numAcceptedQuestions array, e.g.:
        {"data":{"userProfileUserQuestionProgressV2":{"numAcceptedQuestions":[]}}}
    A real user (even one who has solved 0 problems) gets back one entry per difficulty
    bucket (Easy/Medium/Hard), so an empty list is the actual signal for "user not found".
    """
    query = """
    query userProfileUserQuestionProgressV2($userSlug: String!) {
      userProfileUserQuestionProgressV2(userSlug: $userSlug) {
        numAcceptedQuestions { difficulty count }
      }
    }
    """
    data = _post(query, {"userSlug": username})  # let network errors propagate - caller decides fail-open/closed

    progress = data.get("data", {}).get("userProfileUserQuestionProgressV2")
    if progress is None:
        return False
    return len(progress.get("numAcceptedQuestions", [])) > 0


def get_all_time_progress(username: str) -> dict:
    """Returns {'easy': n, 'medium': n, 'hard': n, 'total': n}"""
    query = """
    query userProfileUserQuestionProgressV2($userSlug: String!) {
      userProfileUserQuestionProgressV2(userSlug: $userSlug) {
        numAcceptedQuestions { difficulty count }
      }
    }
    """
    data = _post(query, {"userSlug": username})
    buckets = data.get("data", {}).get("userProfileUserQuestionProgressV2", {}).get(
        "numAcceptedQuestions", []
    )
    result = {"easy": 0, "medium": 0, "hard": 0}
    for b in buckets:
        diff = b["difficulty"].lower()
        if diff in result:
            result[diff] = b["count"]
    result["total"] = sum(result.values())
    return result


def get_recent_accepted_submissions(username: str, limit: int = 20) -> list[dict]:
    query = """
    query recentAcSubmissions($username: String!, $limit: Int!) {
      recentAcSubmissionList(username: $username, limit: $limit) {
        title
        titleSlug
        timestamp
      }
    }
    """
    data = _post(query, {"username": username, "limit": limit})
    return data.get("data", {}).get("recentAcSubmissionList", []) or []


def _get_question_difficulty(title_slug: str) -> str:
    if title_slug in _difficulty_cache:
        return _difficulty_cache[title_slug]

    query = """
    query questionDifficulty($titleSlug: String!) {
      question(titleSlug: $titleSlug) { difficulty }
    }
    """
    try:
        data = _post(query, {"titleSlug": title_slug})
        diff = data.get("data", {}).get("question", {}).get("difficulty", "Medium")
    except Exception:
        diff = "Medium"
    _difficulty_cache[title_slug] = diff
    time.sleep(0.2)  # be polite to the unofficial endpoint
    return diff


def get_todays_activity(username: str) -> dict:
    """
    Returns today's solved count broken down by difficulty, plus all-time totals.
    {'solved_today': n, 'easy': n, 'medium': n, 'hard': n, 'total_all_time': n}
    """
    submissions = get_recent_accepted_submissions(username)
    today_utc = datetime.now(timezone.utc).date()

    seen_today_slugs = set()
    for sub in submissions:
        sub_date = datetime.fromtimestamp(int(sub["timestamp"]), tz=timezone.utc).date()
        if sub_date == today_utc:
            seen_today_slugs.add(sub["titleSlug"])

    counts = {"easy": 0, "medium": 0, "hard": 0}
    for slug in seen_today_slugs:
        diff = _get_question_difficulty(slug).lower()
        if diff in counts:
            counts[diff] += 1

    all_time = get_all_time_progress(username)

    return {
        "solved_today": len(seen_today_slugs),
        "easy": counts["easy"],
        "medium": counts["medium"],
        "hard": counts["hard"],
        "total_all_time": all_time["total"],
    }
