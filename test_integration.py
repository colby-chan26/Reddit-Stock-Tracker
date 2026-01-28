import asyncio
from utils import (
    make_api_call,
    parse_json_for_post_ids,
    parse_json_for_post_content,
    parse_json_for_comment_content,
    parse_json_for_reply_content
)
from stocks_db import StocksDB
from validator import SECTickerValidator
import aiohttp


async def main():
    """Test function for make_api_call, parse_json_for_post_ids, parse_json_for_post_content, and parse_json_for_comment_content"""
    print("🧪 Testing parsing functions and database insertion...\n")
    
    # Initialize database connection and validator
    db = StocksDB()
    validator = SECTickerValidator()
    await validator.load_tickers()
    print("✅ Database connection and validator initialized\n")
    
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
                post_url = f"https://www.reddit.com/r/ValueInvesting/comments/{first_post_id}.json?sort=top&limit=7"
                
                post_data = await make_api_call(post_url, session)
                
                if post_data:
                    # post_data already contains both post and comments data in array format
                    submission_data, post_text, comment_ids = await parse_json_for_post_content(post_data)
                    if submission_data:
                        print(f"✅ Successfully parsed post content")
                        print(f"   Author: {submission_data.author}")
                        print(f"   Score: {submission_data.score}")
                        print(f"   Comment IDs: {comment_ids}\n")
                        
                        # Test 6: Extract tickers and insert post data into database
                        print("Test 6: Extracting tickers from post text and inserting into DB")
                        tickers = validator.validate(post_text)
                        print(f"   Tickers found: {tickers}")
                        if tickers:
                            db.insert(tickers, submission_data)
                        else:
                            print("   ⚠️  No valid tickers found in post")
                        print()
                        
                        # Test 4: Fetch and parse content for the first comment
                        if comment_ids:
                            print("Test 4: Fetching and parsing first comment content")
                            first_comment_id = comment_ids[0]
                            comment_url = f"https://www.reddit.com/r/ValueInvesting/comments/{first_post_id}/comment/{first_comment_id}.json?sort=top&limit=7"
                            
                            comment_data = await make_api_call(comment_url, session)
                            
                            if comment_data:
                                comment_submission_data, comment_text, reply_objects = await parse_json_for_comment_content(comment_data, first_post_id)
                                if comment_submission_data:
                                    print(f"✅ Successfully parsed comment content")
                                    print(f"   Author: {comment_submission_data.author}")
                                    print(f"   Score: {comment_submission_data.score}")
                                    print(f"   Reply Objects: {len(reply_objects)} replies\n")
                                    
                                    # Test 7: Extract tickers and insert comment data into database
                                    print("Test 7: Extracting tickers from comment text and inserting into DB")
                                    tickers = validator.validate(comment_text)
                                    print(f"   Tickers found: {tickers}")
                                    if tickers:
                                        db.insert(tickers, comment_submission_data)
                                    else:
                                        print("   ⚠️  No valid tickers found in comment")
                                    print()
                                    
                                    # Test 5: Fetch and parse content for the first reply
                                    if reply_objects:
                                        print("Test 5: Parsing first reply content")
                                        first_reply = reply_objects[0]
                                        
                                        reply_submission_data, reply_text = await parse_json_for_reply_content(first_reply, first_post_id)
                                        if reply_submission_data:
                                            print(f"✅ Successfully parsed reply content")
                                            print(f"   Author: {reply_submission_data.author}")
                                            print(f"   Score: {reply_submission_data.score}")
                                            print(f"   Type: {reply_submission_data.type.name}\n")
                                            
                                            # Test 8: Extract tickers and insert reply data into database
                                            print("Test 8: Extracting tickers from reply text and inserting into DB")
                                            tickers = validator.validate(reply_text)
                                            print(f"   Tickers found: {tickers}")
                                            if tickers:
                                                db.insert(tickers, reply_submission_data)
                                            else:
                                                print("   ⚠️  No valid tickers found in reply")
                                            print()
                                        else:
                                            print("❌ Failed to parse reply content\n")
                                else:
                                    print("❌ Failed to parse comment content\n")
                            else:
                                print("❌ Failed to fetch comment data\n")
                    else:
                        print("❌ Failed to parse post content\n")
                else:
                    print("❌ Failed to fetch post content or comments\n")
            else:
                print("❌ Failed to parse post IDs\n")
        else:
            print("❌ Failed to fetch data\n")
    
    # Close database connection
    db.close()
    print("✅ Database connection closed")


if __name__ == "__main__":
    asyncio.run(main())
