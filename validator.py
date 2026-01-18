import asyncio
import aiohttp
import os
import json
from typing import Set
from dotenv import load_dotenv
from gliner import GLiNER

SEC_URL = "https://www.sec.gov/files/company_tickers.json"
TICKERS_CACHE_FILE = "tickers_cache.json"

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
        Tries to fetch from SEC, saves to JSON cache on success.
        Falls back to cached JSON, then hardcoded FALLBACK if needed.
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
                    
                    # Save to JSON cache for future use
                    try:
                        with open(TICKERS_CACHE_FILE, 'w') as f:
                            json.dump(list(self.valid_tickers), f, indent=2)
                        print(f"💾 Tickers saved to {TICKERS_CACHE_FILE}")
                    except Exception as save_error:
                        print(f"⚠️  Warning: Could not save tickers cache: {save_error}")
                    
                    return
                    
            except Exception as e:
                print(f"❌ Failed to load SEC data: {e}")
                
                # Try to load from cached JSON first
                try:
                    if os.path.exists(TICKERS_CACHE_FILE):
                        with open(TICKERS_CACHE_FILE, 'r') as f:
                            cached_tickers = json.load(f)
                        self.valid_tickers = set(cached_tickers)
                        print(f"✅ Loaded {len(self.valid_tickers)} tickers from cache: {TICKERS_CACHE_FILE}")
                        return
                except Exception as cache_error:
                    print(f"⚠️  Could not load from cache: {cache_error}")
                
                # Final fallback - use empty set and warn user
                print(f"❌ CRITICAL: No ticker data available. Please ensure SEC.gov is accessible or cache file exists.")
                self.valid_tickers = set()

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
