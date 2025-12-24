import asyncio
import time
import aiohttp
import os
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass
from enum import Enum
from dotenv import load_dotenv

load_dotenv()

MAX_CONCURRENT_REQUESTS = 15 
NUM_TOP_POSTS = 10 
NUM_COMMENTS_PER_POST = 5
MAX_RETRIES = 1
class SubmissionType(Enum):
    POST = 0
    COMMENT = 1
    REPLY = 2
@dataclass
class SubmissionData:
    """Data class to store parsed Reddit submission information."""
    submission_id: str
    score: int
    created_utc: int
    author: str
    subreddit: str
    type: SubmissionType

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
    headers = {"User-Agent": f"MyStockScraper/1.0 {os.getenv("EMAIL")}"}
    
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

async def parse_json_for_comment_content(raw_json: Dict[str, Any], type: SubmissionType) -> Tuple[SubmissionData | None, str]:
    """Parses the JSON response for a single comment or reply, returning a single string of all relevant text."""
    
    # Concatenate the comment body and all reply bodies into one string
    comment_body = raw_json.get("body", "")
    replies_text = " ".join(raw_json.get("replies", []))
    
    full_thread_text = f"{comment_body} {replies_text}"
    
    print(f"  💡 Parsed Comment Thread JSON: Consolidated comment and {len(raw_json.get('replies', []))} replies into one text block.")
    return full_thread_text

async def parse_json_for_reply_content(raw_json: Dict[str, Any], type: SubmissionType) -> Tuple[SubmissionData | None, str]:
    """Parses the JSON response for a single comment or reply, returning a single string of all relevant text."""
    
    # Concatenate the comment body and all reply bodies into one string
    comment_body = raw_json.get("body", "")
    replies_text = " ".join(raw_json.get("replies", []))
    
    full_thread_text = f"{comment_body} {replies_text}"
    
    print(f"  💡 Parsed Comment Thread JSON: Consolidated comment and {len(raw_json.get('replies', []))} replies into one text block.")
    return full_thread_text

# --- TEXT PROCESSING FUNCTION (CPU-BOUND) ---

def process_text(text_content: str, source_description: str) -> List[str]:
    """Finds and extracts tickers from the cleaned text content."""

        # Extract metadata from the post    # This function uses regex or other NLP methods to identify symbols (e.g., $TSLA, GME).
    # This is a synchronous, CPU-bound operation.
    time.sleep(0.001) 
    
    # Simulate finding a ticker
    simulated_ticker = f"TKR_{source_description.split(' ')[0]}_{len(text_content) % 100}"
    return [simulated_ticker]

# --- CORE ASYNCHRONOUS WORKFLOW FUNCTIONS ---

async def main():
    """Test function for make_api_call, parse_json_for_post_ids, and parse_json_for_post_content"""
    print("🧪 Testing make_api_call, parse_json_for_post_ids, and parse_json_for_post_content...\n")
    
    # Create a session for the test
    async with aiohttp.ClientSession() as session:
        # Test 1: Fetch JSON from Reddit
        print("Test 1: Fetching JSON from Reddit")
        url = "https://www.reddit.com/r/ValueInvesting/top.json?limit=10&t=week"
        result = await make_api_call(url, session)
        if result:
            print(f"✅ Success! Retrieved data from Reddit\n")
            
            # Test 2: Parse the JSON for post IDs
            print("Test 2: Parsing JSON for post IDs")
            post_ids = await parse_json_for_post_ids(result)
            if post_ids:
                print(f"✅ Successfully parsed {len(post_ids)} post IDs")
                print(f"Post IDs: {post_ids}\n")
                
                # Test 3: Fetch and parse content for the first post
                print("Test 3: Fetching and parsing post content")
                first_post_id = post_ids[0]
                post_url = f"https://www.reddit.com/r/ValueInvesting/comments/{first_post_id}.json"
                
                post_data = await make_api_call(post_url, session)
                
                if post_data:
                    # post_data already contains both post and comments data in array format
                    submission_data, post_text, comment_ids = await parse_json_for_post_content(post_data)
                    print(f"✅ Successfully parsed post content")
                    print(f"   Author: {submission_data.author}")
                    print(f"   Score: {submission_data.score}")
                    print(f"   Comment IDs: {comment_ids}\n")
                else:
                    print("❌ Failed to fetch post content or comments\n")
            else:
                print("❌ Failed to parse post IDs\n")
        else:
            print("❌ Failed to fetch data\n")

if __name__ == "__main__":
    asyncio.run(main())

