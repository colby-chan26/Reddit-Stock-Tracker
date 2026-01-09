import asyncio
import time
import aiohttp
import os
from typing import List, Tuple, Dict, Any
from custom_types import SubmissionData, SubmissionType
from dotenv import load_dotenv

load_dotenv()

MAX_CONCURRENT_REQUESTS = 15 
NUM_TOP_POSTS = 10 
NUM_COMMENTS_PER_POST = 5
MAX_RETRIES = 1

async def simulate_api_call(request_description: str) -> Dict[str, Any]:
    """A placeholder for a single, distinct network request, returning a simulated JSON response."""
    await asyncio.sleep(0.5) 
    
    # Simulate different JSON structures based on the request type
    if "Post Listing" in request_description:
        # Simulate initial list of post IDs
        return {"kind": "Listing", "data": [f"P{i}" for i in range(1, NUM_TOP_POSTS + 1)]}
    elif "Post" in request_description and "content" in request_description:
        # Simulate post content retrieval, including comment IDs
        post_id = int(request_description.split(' ')[1])
        return {
            "kind": "Post", 
            "title": f"The Value Case for Stock {post_id}",
            "text": f"This is the detailed post content for stock {post_id}. I think it's undervalued.",
            # Simulate the comment IDs being nested in the response
            "top_comment_ids": [f"C{i}_{post_id}" for i in range(1, NUM_COMMENTS_PER_POST + 1)]
        }
    elif "Comment" in request_description and "Replies" in request_description:
        # Simulate a full comment thread with replies
        comment_id = request_description.split(' ')[1]
        return {
            "kind": "CommentThread",
            "body": f"I disagree with the analysis on {comment_id}. The P/E ratio is too high.",
            "replies": [f"Reply to {comment_id}, point 1", f"Reply to {comment_id}, point 2"]
        }
    
    return {"error": "Unknown request type"}

# --- Fetch Data ---

async def make_api_call(url: str, session: aiohttp.ClientSession, params: dict = None, retry_count: int = 0):
    """
    Performs the actual GET request using the shared session.
    """
    # Reddit usually requires a unique User-Agent to avoid 429 (Too Many Requests)
    headers = {"User-Agent": f"MyStockScraper/1.0 {os.getenv("EMAIL")} by u/Ok_Cucumber_3696"}

    print(headers)
    
    try:
        # The 'await' happens here - yielding control while waiting for Reddit
        async with session.get(url, headers=headers, params=params) as response:
            
            # Check for Rate Limits (429) or Errors
            if response.status == 429:
                if retry_count >= MAX_RETRIES:
                    print(f"⚠️ Rate limited on {url}. Max retries exceeded.")
                    return None
                print(f"⚠️ Rate limited on {url}. Sleeping for 60s...")
                await asyncio.sleep(60)
                # Retry once with incremented counter
                return await make_api_call(url, session, params, retry_count + 1)

            response.raise_for_status() # Raise error for 404, 500, etc.
            
            # Return the JSON data directly
            return await response.json()
            
    except Exception as e:
        print(f"❌ Error fetching {url}: {e}")
        return None

# --- JSON PARSING FUNCTIONS (ASYNC as they deal with network results, but mostly CPU-bound) ---

async def parse_json_for_post_ids(raw_json: Dict[str, Any]) -> List[str]:
    """Parses the JSON response from the top 10 list API call."""
    # Navigate through the Reddit JSON structure: data -> children -> data -> id
    post_ids = []
    
    try:
        children = raw_json.get("data", {}).get("children", [])
        for child in children:
            post_id = child.get("data", {}).get("id")
            if post_id:
                post_ids.append(post_id)
    except (KeyError, TypeError) as e:
        print(f"❌ Error parsing post IDs: {e}")
    
    print(f"  💡 Parsed {len(post_ids)} post IDs from listing JSON.")
    print(post_ids)
    return post_ids

async def extract_submission_data(submission_json: Dict[str, Any], submission_type: SubmissionType) -> Tuple[str, SubmissionData]:
    # Extract the main text content for ticker extraction
    # For posts: use selftext, fall back to body for comments/replies
    text = submission_json.get('selftext', '').strip() or submission_json.get('body', '').strip()
    title = submission_json.get('title', '') or ''
    post_text_and_title = text + title
    
    # Extract metadata from the post
    submission_data = SubmissionData(
        submission_id=submission_json.get("id", ""),
        score=submission_json.get("score", 0),
        created_utc=submission_json.get("created_utc", 0),
        author=submission_json.get("author", "Unknown"),
        subreddit=submission_json.get("subreddit", "Unknown"),
        type=submission_type
    )
    
    return post_text_and_title, submission_data

async def parse_json_for_post_content(raw_json: List[Dict[str, Any]]) -> Tuple[SubmissionData | None, str, List[str]]:
    try:
        # Extract the first 5 comment IDs from json[1].data.children[0:5]
        comment_ids = []
        comments_data = raw_json[1]["data"]["children"]
        for i, comment in enumerate(comments_data):
            if i >= NUM_COMMENTS_PER_POST:
                break
            comment_id = comment.get("data", {}).get("id")
            if comment_id:
                comment_ids.append(comment_id)

        # Extract submission data from json[0].data.children[0].data
        post_data = raw_json[0]["data"]["children"][0]["data"]
        
        # Extract submission data using helper function
        post_text_and_title, submission_data = await extract_submission_data(post_data, SubmissionType.POST)
        
        print(f"  💡 Parsed Post JSON: {submission_data.author} | Score: {submission_data.score} | {len(comment_ids)} comment IDs.")
        return submission_data, post_text_and_title, comment_ids
        
    except (KeyError, TypeError, IndexError) as e:
        print(f"❌ Error parsing post content: {e}")
        return None, "", []

async def parse_json_for_comment_content(raw_json: List[Dict[str, Any]]) -> Tuple[SubmissionData | None, str, List]:
    try:
        # Extract comment data from json[1].data.children[0].data
        comment_data = raw_json[1]["data"]["children"][0]["data"]
        
        # Extract reply objects from json[1].data.children[0].data.replies.data.children
        reply_objects = []
        replies_structure = comment_data.get("replies", {})
        if isinstance(replies_structure, dict):
            replies_children = replies_structure.get("data", {}).get("children", [])
            reply_objects.extend(replies_children)
        
        # Extract submission data using helper function
        comment_text_and_title, submission_data = await extract_submission_data(comment_data, SubmissionType.COMMENT)
        
        print(f"  💡 Parsed Comment JSON: {submission_data.author} | Score: {submission_data.score} | {len(reply_objects)} replies.")
        return submission_data, comment_text_and_title, reply_objects
        
    except (KeyError, TypeError, IndexError) as e:
        print(f"❌ Error parsing comment content: {e}")
        return None, "", []

async def parse_json_for_reply_content(raw_json: Dict[str, Any]) -> Tuple[SubmissionData | None, str]:
    """Parses the JSON response for a single reply, extracting reply data and text."""
    
    try:
        # Extract reply data from the raw_json
        reply_data = raw_json.get("data", raw_json)
        
        # Extract submission data using helper function
        reply_text, submission_data = await extract_submission_data(reply_data, SubmissionType.REPLY)
        
        print(f"  💡 Parsed Reply JSON: {submission_data.author} | Score: {submission_data.score}")
        return submission_data, reply_text
        
    except (KeyError, TypeError, IndexError) as e:
        print(f"❌ Error parsing reply content: {e}")
        return None, ""

# --- TEXT PROCESSING FUNCTION (CPU-BOUND) ---

def process_text(text_content: str, source_description: str) -> List[str]:
    """Finds and extracts tickers from the cleaned text content."""

        # Extract metadata from the post    # This function uses regex or other NLP methods to identify symbols (e.g., $TSLA, GME).
    # This is a synchronous, CPU-bound operation.
    time.sleep(0.001) 
    
    # Simulate finding a ticker
    simulated_ticker = f"TKR_{source_description.split(' ')[0]}_{len(text_content) % 100}"
    return [simulated_ticker]

