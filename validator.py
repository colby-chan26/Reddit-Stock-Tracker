import asyncio
import aiohttp
import os
from fallback import FALLBACK
from typing import Set
from dotenv import load_dotenv
from gliner import GLiNER
# import pyperclip
# import re
# import json

SEC_URL = "https://www.sec.gov/files/company_tickers.json"

EXCLUSION_LIST = {
    "EDIT", "AI", "WELL", "LOT",
}

class SECTickerValidator:
    def __init__(self):
        load_dotenv()
        self.valid_tickers: Set[str] = set()
        
        # Load GLiNER model
        print("📥 Loading GLiNER model (first run will download model)...")
        self.gliner_model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")
        print("✅ GLiNER model loaded successfully")
        
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
                    
                    # Store as set
                    for entry in data.values():
                        ticker = entry['ticker']
                        self.valid_tickers.add(ticker)
                        
                    print(f"✅ SEC Data Loaded: {len(self.valid_tickers)} tickers.")
            except Exception as e:
                print(f"❌ Failed to load SEC data: {e}")
                self.valid_tickers = FALLBACK

    def validate(self, text: str) -> list:
        """
        Extract tickers from text using GLiNER model and SEC database validation.
        
        1. Use GLiNER model to detect stock tickers and companies in text
        2. Validate detected tickers against SEC database
        3. Return sorted unique tickers
        """
        tickers_found = set()
        
        # Use GLiNER to detect tickers and companies
        try:
            labels = ["stock ticker"]
            
            # Split long text into chunks to avoid truncation (GLiNER max is 384 tokens)
            # Approximate 1 token = 4 chars, so 384 tokens ≈ 1500 chars
            max_chars = 1200  # Safe limit to avoid truncation
            
            if len(text) > max_chars:
                # Split by newlines to keep context together
                lines = text.split('\n')
                chunks = []
                current_chunk = ""
                
                for line in lines:
                    if len(current_chunk) + len(line) + 1 <= max_chars:
                        current_chunk += line + "\n"
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = line + "\n"
                
                if current_chunk:
                    chunks.append(current_chunk.strip())
            else:
                chunks = [text]
            
            # Process each chunk
            for chunk in chunks:
                entities = self.gliner_model.predict_entities(chunk, labels, threshold=0.5)
                
                for entity in entities:
                    # Extract the ticker/company text
                    ticker_text = entity['text'].strip()
                    
                    # Remove $ prefix if present
                    if ticker_text.startswith('$'):
                        ticker_text = ticker_text[1:]
                    
                    # Convert to uppercase for SEC lookup
                    ticker_upper = ticker_text.upper()
                    
                    # Validate against SEC database and exclusion list
                    if ticker_upper in self.valid_tickers and ticker_upper not in EXCLUSION_LIST:
                        tickers_found.add(ticker_upper)
                    
        except Exception as e:
            print(f"⚠️  Error during ticker detection: {e}")
        
        return sorted(list(tickers_found))

# --- Test ---
test_posts = [
"""
Enough of Nebius, Google, Meta, NovoNordisk, Adobe, Fiserv and co.
Many are great, other can be debated, but there are at least 2 posts a day about them here.

Any stock you are eyeing (or buying) that you rarely hear about and that gets you excited for the futur ? They might not be in the "value investing" zone as of today - keeping a close eye on them for better entry or reinforcement points.

I grew an interest in

Manhattan Associates inc.: The complexity of modern supply chains is increasing, Manhattan Associates is well positioned as a key Warehouse Management Systems. they have little to no debt, and massive switching costs.

maybe a bit more hype, but i also like more and more Investor AB: European Berkshire like family run business that have high conviction on northern EU companies that I myself enjoyed quite a lot analysing before I knew them (Atlas Copco, ABB and so on).

EDIT: Well, that was a popular post. A lot of interesting takes. I must admit I am a bit surprised that, for many, non-hyped or under-radar stocks are mostly hyper growth micro and small-caps.

I wanted to add a few more myself (non-US, sorry): ASSA ABLOY AB, Medacta group SA, RELX, Linde (mentioned), Nemetschek, Hexagon AB, Atlas Copco
""",
]

async def main():
    # 1. Initialize Validator
    validator = SECTickerValidator()
    
    # 2. Load Data (The "One-Time" API Call)
    await validator.load_tickers()
    
    # 3. Copy valid_tickers to clipboard
    # if CLIPBOARD_AVAILABLE:
    #     try:
    #         tickers_json = json.dumps(sorted(list(validator.valid_tickers)), indent=2)
    #         pyperclip.copy(tickers_json)
    #         print(f"✅ Copied {len(validator.valid_tickers)} entries to clipboard!")
    #     except Exception as e:
    #         print(f"⚠️  Failed to copy to clipboard: {e}")
    # else:
    #     print("⚠️  pyperclip not available. Install with: pip install pyperclip")
    
    print("-" * 60)
    print("Testing Ticker Extraction on Social Media Posts")
    print("-" * 60)
    
    # Test posts from various social media scenarios
    
    # Test each post
    for i, post in enumerate(test_posts, 1):
        valid_found = validator.validate(post)
        print(f"\n[Post {i}]")
        print(f"Text: {post[:70]}..." if len(post) > 70 else f"Text: {post}")
        print(f"Tickers Found: {valid_found if valid_found else 'None'}")

if __name__ == "__main__":
    asyncio.run(main())