
import requests, json

query = """
query userProfileUserQuestionProgressV2($userSlug: String!) {
  userProfileUserQuestionProgressV2(userSlug: $userSlug) {
    numAcceptedQuestions { difficulty count }
  }
}
"""

def check(username):
    print(f">>> checking: {username}", flush=True)
    try:
        resp = requests.post(
            "https://leetcode.com/graphql",
            json={"query": query, "variables": {"userSlug": username}},
            headers={"Content-Type": "application/json", "Referer": "https://leetcode.com"},
            timeout=15,
        )
        print("status:", resp.status_code, flush=True)
        print("raw text:", resp.text[:2000], flush=True)
    except Exception as e:
        print("EXCEPTION:", repr(e), flush=True)

check("asdkjaskldjaklsdj123notreal")

