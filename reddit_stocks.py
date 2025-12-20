import asyncio
import time
import aiohttp
from typing import List, Tuple
from utils import (
    parse_json_for_post_ids,
    parse_json_for_post_content,
    parse_json_for_comment_thread,
    process_text,
    simulate_api_call,
)
from validator import (
  SECTickerValidator
)

# --- CONCURRENCY PARAMETERS ---

MAX_CONCURRENT_REQUESTS = 15 
NUM_TOP_POSTS = 10 
NUM_COMMENTS_PER_POST = 5

# --- HELPER FUNCTIONS (Simulating API Calls and Processing) ---

async def fetch_full_comment_thread(comment_id: str, post_id: int, semaphore: asyncio.Semaphore) -> List[str]:
    """Step 3: Fetches the comment and all its nested replies (1 API CALL), then parses and processes."""
    
    request_desc = f"Comment {comment_id} and all Replies (Post {post_id})"
    
    # --- Part 1: API Call (I/O-Bound) ---
    async with semaphore:
        raw_thread_json = await simulate_api_call(request_desc)
        print(f"    ✅ Completed API call: {request_desc}")
            
    # --- Part 2: JSON Parsing (CPU-Bound) ---
    thread_text = await parse_json_for_comment_thread(raw_thread_json)
    
    # --- Part 3: Text Processing (CPU-Bound) ---
    return process_text(thread_text, request_desc)


async def fetch_post_data_and_comment_ids(post_id: int, semaphore: asyncio.Semaphore) -> Tuple[List[str], List[str]]:
    """Step 2: Fetches the post body (1 API CALL), parses, and extracts comment IDs for the next block."""
    
    request_desc = f"Post {post_id} content"

    # --- Part 1: API Call (I/O-Bound) ---
    async with semaphore:
        raw_post_json = await simulate_api_call(request_desc)
        print(f"  ✅ Completed API call: {request_desc}")

    # --- Part 2: JSON Parsing (CPU-Bound) ---
    post_text, comment_ids = await parse_json_for_post_content(raw_post_json)

    # --- Part 3: Text Processing (CPU-Bound) ---
    post_tickers = process_text(post_text, request_desc)
    
    return post_tickers, comment_ids


async def main():
    # 1. Initialize Validator
    validator = SECTickerValidator()

    # 2. Load Data (The "One-Time" API Call)
    await validator.load_tickers()

    """Main entry point for the 61-request asynchronous workflow."""
    
    print(f"--- Starting Final 61-Request Workflow (Parse/Process Decoupled) ---")
    print(f"Max Concurrent Requests (Semaphore): {MAX_CONCURRENT_REQUESTS}")
    print(f"Total I/O Operations: 1 (Listing) + 10 (Posts) + 50 (Comments) = 61")
    print("-" * 60)

    SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    all_tickers = []

    async with aiohttp.ClientSession() as session:
    
      # --- Block 1: Sequential Fetch and Parse (1 API Call) ---
      print("\n[BLOCK 1] Fetching and Parsing top post IDs...")
      raw_listing_json = await simulate_api_call("Top 10 Post Listing")
      post_ids = await parse_json_for_post_ids(raw_listing_json)
      print(f"Total Post IDs to process: {len(post_ids)}")

      # --- Block 2: Concurrent Post Fetch (10 API Calls) ---
      
      # Create 10 concurrent tasks to fetch post body and extract comment IDs.
      post_tasks = [fetch_post_data_and_comment_ids(int(p_id.split('P')[-1]), SEMAPHORE) for p_id in post_ids]
          
      print(f"\n[BLOCK 2] Launching {len(post_tasks)} concurrent Post Fetches (10 API calls)...")
      post_results = await asyncio.gather(*post_tasks)
      
      # Consolidate results and prepare for the next block
      comment_fetch_tasks = []
      for post_tickers, comment_ids in post_results:
          all_tickers.extend(post_tickers)
          
          # Create the reply fetch tasks for Block 3
          for comment_id in comment_ids:
              # Extract parent post ID for tracking (e.g., C1_5 -> post_id=5)
              parent_post_id = int(comment_id.split('_')[-1]) 
              task = fetch_full_comment_thread(comment_id, parent_post_id, SEMAPHORE)
              comment_fetch_tasks.append(task)
              
      # --- Block 3: Highly Concurrent Comment/Reply Fetch (50 API Calls) ---

      print(f"\n[BLOCK 3] Launching {len(comment_fetch_tasks)} highly concurrent Comment/Reply Fetches (50 API calls)...")
      comment_results = await asyncio.gather(*comment_fetch_tasks)

      # Consolidate final results
      for ticker_list in comment_results:
          all_tickers.extend(ticker_list)

      # --- Final Consolidation ---
    
    print("\n" + "=" * 60)
    print(f"Workflow Complete. Total API Calls: 61")
    print(f"Total Unique Tickers Found: {len(set(all_tickers))}")
    print("=" * 60)
    

if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(main()) 
    end_time = time.time()
    
    print(f"\nTotal execution time: {end_time - start_time:.2f} seconds")