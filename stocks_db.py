import psycopg
import os
from dotenv import load_dotenv
from typing import List
from datetime import datetime, timezone
from custom_types import SubmissionData

load_dotenv()

class StocksDB:
    def __init__(self):
        self.conn = psycopg.connect(
            host=os.getenv("DB_HOST"), 
            dbname=os.getenv("DB_NAME"), 
            user=os.getenv("DB_USER"), 
            password=os.getenv("DB_PASSWORD"), 
            port=os.getenv("DB_PORT")
            # os.getenv('DB_URL')
        )
        self.cur = self.conn.cursor()
        
        # Create enum type if it doesn't exist
        self.cur.execute("""
            DO $$ BEGIN
                CREATE TYPE submission_type AS ENUM ('POST', 'COMMENT', 'REPLY');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """)
        
        # Create table if it doesn't exist
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS stocks (
                id SERIAL PRIMARY KEY,
                submission_id VARCHAR(30),
                ticker CHAR(5),
                author VARCHAR(30), 
                subreddit VARCHAR(30),
                score SMALLINT,
                "type" submission_type,
                created_utc TIMESTAMPTZ
            )
        """)
        
        self.conn.commit()

    def insert(self, tickers: List[str], submission: SubmissionData):
        """Insert each ticker with the submission data into the database."""
        # Convert Unix timestamp to datetime
        created_dt = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
        
        # Insert each ticker as a separate row
        for ticker in tickers:
            self.cur.execute("""
                INSERT INTO stocks (submission_id, ticker, author, subreddit, score, "type", created_utc)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                submission.submission_id,
                ticker,
                submission.author,
                submission.subreddit,
                submission.score,
                submission.type.value,
                created_dt
            ))
        
        # Commit after all inserts
        self.conn.commit()
        print(f'✅ Inserted {len(tickers)} ticker(s) into DB')
        

    
    def close(self):
        """Close the cursor and connection."""
        self.cur.close()
        self.conn.close()

def main():
    stocksDB = StocksDB()

main()
    