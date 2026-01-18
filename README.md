# 🚀 Reddit Stock Tracker

> _"To the moon!"_ - Every Reddit trader, probably

Ever wondered what stocks the Reddit hivemind is buzzing about? Wonder no more! This tool scrapes Reddit's investing communities, extracts stock tickers using NLP, validates them against the SEC's official database, and stores everything in a database for analytical pleasure.

## 🎯 What Does This Thing Do?

- **🤖 Ticker Detection**: Uses GLiNER (a fancy neural network) to spot stock tickers in Reddit posts, comments, and replies
- **✅ SEC Validation**: Every ticker is validated against the official SEC database (because we don't want to track $YOLO or $MOON as real stocks)
- **⚡ Concurrency**: Concurrent async operations mean we can process hundreds of posts in seconds
- **💾 Database Storage**: Writes to PostgreSQL databases
- **📊 Deep Scraping**: Doesn't just grab posts - goes deep into comments and replies too
- **🎛️ Fully Configurable**: Control everything from concurrency limits to how deep the scraper goes

## 🏗️ Architecture

```
Reddit API → Async Scraper → GLiNER → SEC Validator → PostgreSQL
     ↓            ↓              ↓            ↓           ↓
  Posts      Comments        Tickers     Validation    Analytics
```

## 🛠️ Installation

**Prerequisites:**

- Python 3.10+
- PostgreSQL databases (local or remote)

> ⚠️ **IMPORTANT: Local Execution Only**
>
> This script **MUST be run on your local machine** and **cannot run behind a VPN**.
>
> Why? The Reddit API is accessed without an API key (using public JSON endpoints), which means:
>
> - Reddit's servers need to see your real residential IP address
> - VPNs, proxies, and cloud servers will likely be blocked or rate-limited aggressively
> - Running from cloud environments (AWS, GCP, Azure, etc.) won't work reliably
> - **Rate Limit: 100 API calls per 10 minutes** - This is Reddit's limit for unauthenticated requests
>
> I tried deploying this with GitHub Actions workflows for automated runs, but GitHub's runner IPs are immediately blocked by Reddit (they are real sticklers about their data). I've included the yaml file if you're interested but
> without an API key, it'll get blocked.
>
> **TL;DR:** Turn off your VPN, run this from your laptop/desktop, and Reddit will be happy.

**Quick Start:**

```bash
# Clone
git clone https://github.com/colby-chan26/Reddit-Stock-Tracker
cd Reddit-Stock-Tracker

# Install dependencies
uv sync

# Set up your environment variables
cp .env.example .env
# Edit .env with your database credentials and email
```

**Environment Variables:**

Create a `.env` file with:

```env
# Database
DB_URL=postgresql://user:password@host:port/database

# SEC.gov requires your email
EMAIL=your.email@example.com
```

## 🎮 Usage

### Basic Usage

```bash
# Scrape r/wallstreetbets with default settings
uv run ./reddit_stocks.py wallstreetbets
```

### Advanced Usage

```bash
# Scrape with custom parameters
uv run ./reddit_stocks.py investing \
  --max-concurrent-requests 20 \
  --num-top-posts 25 \
  --num-comments-per-post 10 \
  --num-replies-per-comment 8
```

**Parameters Explained:**

| Flag                        | Default | What It Does                                                                  |
| --------------------------- | ------- | ----------------------------------------------------------------------------- |
| `--max-concurrent-requests` | 15      | How many Reddit API calls to make simultaneously (watch out for rate limits!) |
| `--num-top-posts`           | 15      | Number of top posts to scrape from the subreddit                              |
| `--num-comments-per-post`   | 5       | Comments to grab from each post                                               |
| `--num-replies-per-comment` | 5       | Replies to grab from each comment                                             |

## 📦 What Gets Stored?

Every mention creates a database record with:

- `ticker`: The stock symbol (e.g., AAPL, TSLA)
- `submission_id`: Reddit's unique ID for the post/comment
- `author`: The Reddit username
- `subreddit`: Where it was posted
- `score`: Upvotes (or downvotes)
- `type`: POST, COMMENT, or REPLY
- `created_utc`: When it was posted (with timezone)

## 🎯 How It Works Under The Hood

### Phase 1: The Hunt 🔍

1. Fetch top posts from the target subreddit
2. Extract post IDs and content

### Phase 2: The Deep Dive 🏊

3. For each post, grab the body text and top comments
4. For each comment, grab the replies
5. All happening concurrently with semaphore control

### Phase 3: Scanning

6. GLiNER scans text for stock tickers
7. Handles long text by chunking
8. Validates against SEC's official ticker database
9. Filters out common words that aren't really stocks ()

### Phase 4: The Storage 💾

10. Writes to PostgreSQL databases
11. Saves run metadata to `last_run.json`

## 🎨 Project Structure

```
Reddit-Stock-Tracker/
├── reddit_stocks.py     # Main scraper with the RedditStockTracker class
├── validator.py         # GLiNER AI + SEC validation magic
├── stocks_db.py         # database writer
├── utils.py             # API calls and JSON parsing
├── custom_types.py      # Type definitions
├── tickers_cache.json   # Cached SEC ticker list
├── last_run.json        # Metadata from last run
```

## ⚖️ Extra Info

- This tool is for educational/research purposes
- Respect Reddit's Terms of Service and API rate limits
- SEC data is public domain
- Don't use this for actual financial advice

---

_Remember: Past performance of Reddit stock mentions is not indicative of future results. This is not financial advice. Please don't YOLO your life savings based on what strangers on the internet say._

🚀 **Happy Tracking!** 🚀
