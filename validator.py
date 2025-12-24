import asyncio
import aiohttp
import os
from fallback import FALLBACK
from typing import Set
from dotenv import load_dotenv

SEC_URL = "https://www.sec.gov/files/company_tickers.json"

class SECTickerValidator:
    def __init__(self):
        load_dotenv()
        self.valid_tickers: Set[str] = set()
        
        # CRITICAL: SEC requires a User-Agent with a contact email.
        # Replace this with your actual contact info.
        self.headers = {
            "User-Agent": f"MyRedditStockScraper/1.0 {os.getenv("EMAIL")}",
            "Accept-Encoding": "gzip, deflate",
            "Host": "www.sec.gov"
        }

    async def load_tickers(self):
        """
        One-time startup task using aiohttp.
        """
        print(f"🏛️  Connecting to SEC.gov...")
        
        # We create a temporary session just for this one-off startup task
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(SEC_URL, headers=self.headers) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
                    for entry in data.values():
                        self.valid_tickers.add(entry['ticker'])
                        
                    print(f"✅ SEC Data Loaded: {len(self.valid_tickers)} tickers.")
            except Exception as e:
                print(f"❌ Failed to load SEC data: {e}")
                self.valid_tickers = FALLBACK # Emergency Fallback

    def validate(self, candidate: str) -> bool:
        """
        Checks if a candidate string is a valid SEC ticker.
        """
        # SEC tickers are always uppercase in the JSON
        return candidate.upper() in self.valid_tickers

# --- Test ---

async def main():
    # 1. Initialize Validator
    validator = SECTickerValidator()
    
    # 2. Load Data (The "One-Time" API Call)
    await validator.load_tickers()
    
    print("-" * 40)
    
    # Example: How to use it inside your parsing logic
    # This simulates the "Process Text" step
    raw_text_candidates = ["$AAPL", "msft", "LOVE", "NOW", "XYZ123"]
    
    valid_found = []
    
    for cand in raw_text_candidates:
        # Clean the candidate first (remove $)
        clean_cand = cand.replace("$", "").upper()
        
        # Check against SEC list
        if validator.validate(clean_cand):
            valid_found.append(clean_cand)
        else:
            print(f"   Discarding '{cand}' - Not in SEC database.")
            
    print(f"Final Valid Tickers: {valid_found}")

if __name__ == "__main__":
    asyncio.run(main())