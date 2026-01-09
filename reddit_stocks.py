import argparse
import asyncio
import time
import aiohttp
from typing import List, Tuple
from utils import (
    make_api_call,
    parse_json_for_post_ids,
    parse_json_for_post_content,
    parse_json_for_comment_content,
    parse_json_for_reply_content,
)
from validator import SECTickerValidator
from stocks_db import StocksDB

# --- CONCURRENCY PARAMETERS ---

MAX_CONCURRENT_REQUESTS = 15
NUM_TOP_POSTS = 15
NUM_COMMENTS_PER_POST = 5
NUM_REPLIES_PER_COMMENT = 5

# --- HELPER FUNCTIONS ---

async def fetch_comment_data(
    comment_id: str, 
    post_id: str,
    subreddit: str,
    session: aiohttp.ClientSession,
    validator: SECTickerValidator,
    db: StocksDB,
    semaphore: asyncio.Semaphore
) -> List:
    """Step 3a: Fetches the comment and its nested replies (1 API CALL), then parses and processes the comment.
    
    Returns:
        List of reply objects to process
    """
    
    # --- Part 1: API Call (I/O-Bound) ---
    async with semaphore:
        comment_url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/comment/{comment_id}.json?sort=top&limit={NUM_REPLIES_PER_COMMENT + 2}"
        raw_thread_json = await make_api_call(comment_url, session)
        if not raw_thread_json:
            print(f"    ❌ Failed to fetch comment {comment_id}")
            return []
    
    # --- Part 2: Parse comment and extract replies ---
    comment_submission_data, comment_text, reply_objects = await parse_json_for_comment_content(raw_thread_json)
    
    if comment_submission_data and comment_text:
        # --- Part 3: Extract tickers and insert into DB ---
        tickers = validator.validate(comment_text)
        if tickers:
            db.insert(tickers, comment_submission_data)
    
    return reply_objects


async def fetch_reply_data(
    reply: dict,
    validator: SECTickerValidator,
    db: StocksDB
) -> None:
    """Step 3b: Processes a single reply object.
    
    Args:
        reply: Reply object extracted from the API response
        validator: Ticker validator instance
        db: Database connection instance
    """
    
    # --- Parse the individual reply ---
    reply_submission_data, reply_text = await parse_json_for_reply_content(reply)
    
    if reply_submission_data and reply_text:
        # --- Extract tickers and insert into DB ---
        tickers = validator.validate(reply_text)
        if tickers:
            db.insert(tickers, reply_submission_data)


async def fetch_post_data_and_comment_ids(
    post_id: str,
    subreddit: str,
    session: aiohttp.ClientSession,
    validator: SECTickerValidator,
    db: StocksDB,
    semaphore: asyncio.Semaphore
) -> List[str]:
    """Step 2: Fetches the post body (1 API CALL), parses, extracts tickers, inserts to DB, and returns comment IDs."""
    
    # --- Part 1: API Call (I/O-Bound) ---
    async with semaphore:
        post_url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json?sort=top&limit={NUM_COMMENTS_PER_POST + 2}"
        raw_post_json = await make_api_call(post_url, session)
        if not raw_post_json:
            print(f"  ❌ Failed to fetch post {post_id}")
            return []

    # --- Part 2: JSON Parsing ---
    submission_data, post_text, comment_ids = await parse_json_for_post_content(raw_post_json)

    if submission_data and post_text:
        # --- Part 3: Extract tickers and insert into DB ---
        tickers = validator.validate(post_text)
        if tickers:
            db.insert(tickers, submission_data)
    
    return comment_ids


async def process_subreddit(
    subreddit: str,
    session: aiohttp.ClientSession,
    validator: SECTickerValidator,
    db: StocksDB,
    semaphore: asyncio.Semaphore
) -> None:
    """Process a single subreddit - fetch posts, comments, and replies.
    
    Args:
        subreddit: Name of the subreddit to process
        session: Shared aiohttp session
        validator: Ticker validator instance
        db: Database connection instance
        semaphore: Concurrency control semaphore
    """
    
    print(f"\n{'='*60}")
    print(f"Processing Subreddit: r/{subreddit}")
    print(f"{'='*60}")

    # --- Block 1: Sequential Fetch and Parse (1 API Call) ---
    print("\n[BLOCK 1] Fetching and Parsing top post IDs...")
    listing_url = f"https://www.reddit.com/r/{subreddit}/top.json?limit={NUM_TOP_POSTS}&t=week"
    raw_listing_json = await make_api_call(listing_url, session)
    
    if not raw_listing_json:
        print("❌ Failed to fetch post listing")
        return
        
    post_ids = await parse_json_for_post_ids(raw_listing_json)
    print(f"Total Post IDs to process: {len(post_ids)}")

    # --- Block 2: Concurrent Post Fetch (10 API Calls) ---
    
    # Create concurrent tasks to fetch post body and extract comment IDs.
    post_tasks = [
        fetch_post_data_and_comment_ids(post_id, subreddit, session, validator, db, semaphore) 
        for post_id in post_ids
    ]
        
    print(f"\n[BLOCK 2] Launching {len(post_tasks)} concurrent Post Fetches ({NUM_TOP_POSTS} API calls)...")
    post_results = await asyncio.gather(*post_tasks)
    
    # Consolidate results and prepare for the next block
    comment_fetch_tasks = []
    for comment_ids in post_results:
        # Create the comment/reply fetch tasks for Block 3
        for comment_id in comment_ids:
            # Get the post_id from the current context - we need to track which post this comment belongs to
            # Since we don't have it directly, we'll need to use the first post_id as a reference
            # In a real scenario, you'd want to track this properly
            for i, cids in enumerate(post_results):
                if comment_id in cids:
                    parent_post_id = post_ids[i]
                    break
            else:
                parent_post_id = post_ids[0]  # fallback
                
            task = fetch_comment_data(comment_id, parent_post_id, subreddit, session, validator, db, semaphore)
            comment_fetch_tasks.append(task)
            
    # --- Block 3: Highly Concurrent Comment/Reply Fetch ---

    print(f"\n[BLOCK 3] Launching {len(comment_fetch_tasks)} concurrent Comment Fetches...")
    comment_results = await asyncio.gather(*comment_fetch_tasks)
    
    # Process comment results and prepare individual reply tasks
    reply_tasks = []
    for replies_list in comment_results:
        # Create individual tasks for each reply (no additional API calls needed)
        for reply in replies_list:
            task = fetch_reply_data(reply, validator, db)
            reply_tasks.append(task)
    
    # Execute all reply processing tasks concurrently
    if reply_tasks:
        print(f"\n[BLOCK 3 Continued] Processing {len(reply_tasks)} replies...")
        await asyncio.gather(*reply_tasks)

    print(f"✅ Completed processing r/{subreddit}")

async def main(subreddit: str):
    """Main entry point - processes a single subreddit.
    
    Args:
        subreddit: Name of the subreddit to process
    """
    
    print(f"--- Starting Reddit Stock Tracker Workflow ---")
    print(f"Subreddit to process: r/{subreddit}")
    print(f"Max Concurrent Requests (Semaphore): {MAX_CONCURRENT_REQUESTS}")
    print(f"Posts per subreddit: {NUM_TOP_POSTS}")
    print("-" * 60)

    # Initialize database and validator
    db = StocksDB()
    validator = SECTickerValidator()
    await validator.load_tickers()
    print("✅ Database connection and validator initialized\n")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async with aiohttp.ClientSession() as session:
        # Process the subreddit
        await process_subreddit(subreddit, session, validator, db, semaphore)
    
    # Close database connection
    db.close()
    print("\n" + "=" * 60)
    print(f"Subreddit Processed Successfully!")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Track stock mentions in a Reddit subreddit")
    parser.add_argument(
        "subreddit",
        type=str,
        help="Name of the subreddit to process (without 'r/' prefix)"
    )
    args = parser.parse_args()
    
    start_time = time.time()
    asyncio.run(main(args.subreddit)) 
    end_time = time.time()
    
    print(f"\nTotal execution time: {end_time - start_time:.2f} seconds")
