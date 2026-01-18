import argparse
import asyncio
import time
import aiohttp
import json
from datetime import datetime
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

def save_last_run_date(subreddit: str) -> None:
    """Save the last run date and time to a JSON file.
    
    Args:
        subreddit: Name of the subreddit that was processed
    """
    last_run_data = {
        "subreddit": subreddit,
        "last_run": datetime.now().isoformat(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    try:
        with open("last_run.json", "w") as f:
            json.dump(last_run_data, f, indent=2)
        print(f"\n✅ Last run date saved to last_run.json")
    except Exception as e:
        print(f"\n⚠️  Warning: Could not save last run date: {e}")


# --- MAIN PROCESSOR CLASS ---

class RedditStockTracker:
    """Handles fetching and processing stock mentions from a Reddit subreddit."""
    
    def __init__(
        self,
        subreddit: str,
        session: aiohttp.ClientSession,
        validator: SECTickerValidator,
        db: StocksDB,
        semaphore: asyncio.Semaphore,
        num_top_posts: int,
        num_comments_per_post: int,
        num_replies_per_comment: int
    ):
        """Initialize the Reddit stock tracker.
        
        Args:
            subreddit: Name of the subreddit to process
            session: Shared aiohttp session
            validator: Ticker validator instance
            db: Database connection instance
            semaphore: Concurrency control semaphore
            num_top_posts: Number of top posts to fetch
            num_comments_per_post: Number of comments to fetch per post
            num_replies_per_comment: Number of replies to fetch per comment
        """
        self.subreddit = subreddit
        self.session = session
        self.validator = validator
        self.db = db
        self.semaphore = semaphore
        self.num_top_posts = num_top_posts
        self.num_comments_per_post = num_comments_per_post
        self.num_replies_per_comment = num_replies_per_comment
    
    async def fetch_comment_data(self, comment_id: str, post_id: str) -> List:
        """Step 3a: Fetches the comment and its nested replies (1 API CALL), then parses and processes the comment.
        
        Args:
            comment_id: ID of the comment to fetch
            post_id: ID of the parent post
            
        Returns:
            List of reply objects to process
        """
        # --- Part 1: API Call (I/O-Bound) ---
        async with self.semaphore:
            comment_url = f"https://www.reddit.com/r/{self.subreddit}/comments/{post_id}/comment/{comment_id}.json?sort=top&limit={self.num_replies_per_comment + 2}"
            raw_thread_json = await make_api_call(comment_url, self.session)
            if not raw_thread_json:
                print(f"    ❌ Failed to fetch comment {comment_id}")
                return []
        
        # --- Part 2: Parse comment and extract replies ---
        comment_submission_data, comment_text, reply_objects = await parse_json_for_comment_content(raw_thread_json)
        
        if comment_submission_data and comment_text:
            # --- Part 3: Extract tickers and insert into DB ---
            tickers = self.validator.validate(comment_text)
            if tickers:
                self.db.insert(tickers, comment_submission_data)
        
        return reply_objects
    
    async def fetch_reply_data(self, reply: dict) -> None:
        """Step 3b: Processes a single reply object.
        
        Args:
            reply: Reply object extracted from the API response
        """
        # --- Parse the individual reply ---
        reply_submission_data, reply_text = await parse_json_for_reply_content(reply)
        
        if reply_submission_data and reply_text:
            # --- Extract tickers and insert into DB ---
            tickers = self.validator.validate(reply_text)
            if tickers:
                self.db.insert(tickers, reply_submission_data)
    
    async def fetch_post_data_and_comment_ids(self, post_id: str) -> List[str]:
        """Step 2: Fetches the post body (1 API CALL), parses, extracts tickers, inserts to DB, and returns comment IDs.
        
        Args:
            post_id: ID of the post to fetch
            
        Returns:
            List of comment IDs
        """
        # --- Part 1: API Call (I/O-Bound) ---
        async with self.semaphore:
            post_url = f"https://www.reddit.com/r/{self.subreddit}/comments/{post_id}.json?sort=top&limit={self.num_comments_per_post + 2}"
            raw_post_json = await make_api_call(post_url, self.session)
            if not raw_post_json:
                print(f"  ❌ Failed to fetch post {post_id}")
                return []

        # --- Part 2: JSON Parsing ---
        submission_data, post_text, comment_ids = await parse_json_for_post_content(raw_post_json)

        if submission_data and post_text:
            # --- Part 3: Extract tickers and insert into DB ---
            tickers = self.validator.validate(post_text)
            if tickers:
                self.db.insert(tickers, submission_data)
        
        return comment_ids
    
    async def process(self) -> None:
        """Process the subreddit - fetch posts, comments, and replies."""
        
        print(f"\n{'='*60}")
        print(f"Processing Subreddit: r/{self.subreddit}")
        print(f"{'='*60}")

        # --- Block 1: Sequential Fetch and Parse (1 API Call) ---
        print("\n[BLOCK 1] Fetching and Parsing top post IDs...")
        listing_url = f"https://www.reddit.com/r/{self.subreddit}/top.json?limit={self.num_top_posts}&t=week"
        raw_listing_json = await make_api_call(listing_url, self.session)
        
        if not raw_listing_json:
            print("❌ Failed to fetch post listing")
            return
            
        post_ids = await parse_json_for_post_ids(raw_listing_json)
        print(f"Total Post IDs to process: {len(post_ids)}")

        # --- Block 2: Concurrent Post Fetch ---
        post_tasks = [self.fetch_post_data_and_comment_ids(post_id) for post_id in post_ids]
            
        print(f"\n[BLOCK 2] Launching {len(post_tasks)} concurrent Post Fetches ({self.num_top_posts} API calls)...")
        post_results = await asyncio.gather(*post_tasks)
        
        # Consolidate results and prepare for the next block
        comment_fetch_tasks = []
        for i, comment_ids in enumerate(post_results):
            parent_post_id = post_ids[i]
            for comment_id in comment_ids:
                task = self.fetch_comment_data(comment_id, parent_post_id)
                comment_fetch_tasks.append(task)
                
        # --- Block 3: Highly Concurrent Comment/Reply Fetch ---
        print(f"\n[BLOCK 3] Launching {len(comment_fetch_tasks)} concurrent Comment Fetches...")
        comment_results = await asyncio.gather(*comment_fetch_tasks)
        
        # Process comment results and prepare individual reply tasks
        reply_tasks = []
        for replies_list in comment_results:
            for reply in replies_list:
                task = self.fetch_reply_data(reply)
                reply_tasks.append(task)
        
        # Execute all reply processing tasks concurrently
        if reply_tasks:
            print(f"\n[BLOCK 3 Continued] Processing {len(reply_tasks)} replies...")
            await asyncio.gather(*reply_tasks)

        print(f"✅ Completed processing r/{self.subreddit}")

async def main(
    subreddit: str,
    max_concurrent_requests: int = MAX_CONCURRENT_REQUESTS,
    num_top_posts: int = NUM_TOP_POSTS,
    num_comments_per_post: int = NUM_COMMENTS_PER_POST,
    num_replies_per_comment: int = NUM_REPLIES_PER_COMMENT
):
    """Main entry point - processes a single subreddit.
    
    Args:
        subreddit: Name of the subreddit to process
        max_concurrent_requests: Maximum concurrent API requests
        num_top_posts: Number of top posts to fetch
        num_comments_per_post: Number of comments to fetch per post
        num_replies_per_comment: Number of replies to fetch per comment
    """
    
    print(f"--- Starting Reddit Stock Tracker Workflow ---")
    print(f"Subreddit to process: r/{subreddit}")
    print(f"Max Concurrent Requests (Semaphore): {max_concurrent_requests}")
    print(f"Posts per subreddit: {num_top_posts}")
    print(f"Comments per post: {num_comments_per_post}")
    print(f"Replies per comment: {num_replies_per_comment}")
    print("-" * 60)

    # Initialize database and validator
    db = StocksDB()
    validator = SECTickerValidator()
    await validator.load_tickers()
    print("✅ Database connection and validator initialized\n")

    semaphore = asyncio.Semaphore(max_concurrent_requests)

    async with aiohttp.ClientSession() as session:
        # Create tracker and process the subreddit
        tracker = RedditStockTracker(
            subreddit=subreddit,
            session=session,
            validator=validator,
            db=db,
            semaphore=semaphore,
            num_top_posts=num_top_posts,
            num_comments_per_post=num_comments_per_post,
            num_replies_per_comment=num_replies_per_comment
        )
        await tracker.process()
    
    # Close database connection
    db.close()
    
    # Save last run date
    save_last_run_date(subreddit)
    
    print("\n" + "=" * 60)
    print(f"Subreddit Processed Successfully!")
    print("=" * 60)


def setup_argument_parser() -> argparse.ArgumentParser:
    """Configure and return the argument parser.
    
    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(description="Track stock mentions in a Reddit subreddit")
    parser.add_argument(
        "subreddit",
        type=str,
        help="Name of the subreddit to process (without 'r/' prefix)"
    )
    parser.add_argument(
        "--max-concurrent-requests",
        type=int,
        default=MAX_CONCURRENT_REQUESTS,
        help=f"Maximum concurrent API requests (default: {MAX_CONCURRENT_REQUESTS})"
    )
    parser.add_argument(
        "--num-top-posts",
        type=int,
        default=NUM_TOP_POSTS,
        help=f"Number of top posts to fetch (default: {NUM_TOP_POSTS})"
    )
    parser.add_argument(
        "--num-comments-per-post",
        type=int,
        default=NUM_COMMENTS_PER_POST,
        help=f"Number of comments to fetch per post (default: {NUM_COMMENTS_PER_POST})"
    )
    parser.add_argument(
        "--num-replies-per-comment",
        type=int,
        default=NUM_REPLIES_PER_COMMENT,
        help=f"Number of replies to fetch per comment (default: {NUM_REPLIES_PER_COMMENT})"
    )
    return parser

if __name__ == "__main__":
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    start_time = time.time()
    asyncio.run(main(
        args.subreddit,
        args.max_concurrent_requests,
        args.num_top_posts,
        args.num_comments_per_post,
        args.num_replies_per_comment
    )) 
    end_time = time.time()
    
    print(f"\nTotal execution time: {end_time - start_time:.2f} seconds")
