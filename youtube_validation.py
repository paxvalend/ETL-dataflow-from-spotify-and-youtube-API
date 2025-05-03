import psycopg2
import pandas as pd
import re
import logging
from datetime import datetime
import access
import sys
from difflib import SequenceMatcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('youtube_cleaner.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'host': access.DB_HOST,
    'database': access.DB_NAME,
    'user': access.DB_USER,
    'password': access.DB_PASSWORD,
    'port': access.DB_PORT
}
SCHEMA = 'test_stored'

def get_db_connection():
    """Establish database connection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(f"SET search_path TO {SCHEMA}, public;")
        logger.info("Database connection established")
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}", exc_info=True)
        raise

def normalize_text(text):
    """Normalize text for comparison - only lowercase, keep special chars"""
    if not text or pd.isna(text):
        return ""
    return str(text).lower().strip()

def similarity_ratio(a, b):
    """Calculate similarity ratio between two strings"""
    return SequenceMatcher(None, a, b).ratio()

def is_match(original, found, video_title):
    """Check if original and found values match video title with 80% word match"""
    if not original or pd.isna(original):
        return False
    
    # Normalize all texts (only lowercase, keep special chars)
    original_norm = normalize_text(original)
    found_norm = normalize_text(found)
    title_norm = normalize_text(video_title)
    
    # Check direct inclusion
    if original_norm in title_norm:
        return True
    
    if found_norm and found_norm in title_norm:
        return True
    
    # Split into words and check partial matches
    original_words = original_norm.split()
    title_words = title_norm.split()
    
    # Count matching words
    match_count = 0
    for o_word in original_words:
        for t_word in title_words:
            if similarity_ratio(o_word, t_word) >= 0.8:  # 80% similarity threshold
                match_count += 1
                break
    
    # Calculate match percentage
    match_percentage = match_count / len(original_words) if original_words else 0
    
    return match_percentage >= 0.8  # At least 80% of words must match

def validate_row(row):
    """Validate a single row of data"""
    try:
        # Check artist match (if artist exists)
        artist_valid = True  # Default valid if no artist specified
        if row['original_artist'] and not pd.isna(row['original_artist']):
            artist_valid = is_match(
                row['original_artist'], 
                row['artist_found'], 
                row['video_title']
            )
        
        # Check song title match (always required)
        title_valid = is_match(
            row['song_title'], 
            row['song_title_found'], 
            row['video_title']
        )
        
        return artist_valid and title_valid
    except Exception as e:
        logger.error(f"Validation error for row {row.get('code')}: {str(e)}")
        return False

def create_clean_table(conn):
    """Create the cleaned data table if not exists"""
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA}.youtube_cleaned_data (
                id SERIAL PRIMARY KEY,
                code VARCHAR(255) UNIQUE NOT NULL,
                channel_id VARCHAR(255),
                original_artist VARCHAR(255),
                song_title VARCHAR(255),
                video_id VARCHAR(255),
                video_title VARCHAR(255),
                channel_name VARCHAR(255),
                views VARCHAR(255),
                artist_found VARCHAR(255),
                song_title_found VARCHAR(255),
                video_url TEXT,
                upload_date DATE,
                ingest_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid BOOLEAN
            )
            """)
            conn.commit()
            logger.info("Clean table created/verified")
    except Exception as e:
        logger.error(f"Error creating clean table: {str(e)}")
        conn.rollback()
        raise

def process_data():
    """Main processing function"""
    conn = None
    try:
        conn = get_db_connection()
        create_clean_table(conn)
        
        # Fetch all data from youtube_metadata
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {SCHEMA}.youtube_metadata")
            columns = [desc[0] for desc in cur.description]
            data = cur.fetchall()
        
        if not data:
            logger.info("No data found in youtube_metadata table")
            return
        
        df = pd.DataFrame(data, columns=columns)
        logger.info(f"Processing {len(df)} records from youtube_metadata")
        
        # Process each record
        for _, row in df.iterrows():
            try:
                valid = validate_row(row)
                
                # Prepare data for insertion
                clean_data = {
                    'code': row['code'],
                    'channel_id': row['channel_id'],
                    'original_artist': row['original_artist'],
                    'song_title': row['song_title'],
                    'video_id': row['video_id'],
                    'video_title': row['video_title'],
                    'channel_name': row['channel_name'],
                    'views': row['views'],
                    'artist_found': row['artist_found'],
                    'song_title_found': row['song_title_found'],
                    'video_url': row['video_url'],
                    'upload_date': row['upload_date'],
                    'valid': valid
                }
                
                # Insert or update in cleaned table
                with conn.cursor() as cur:
                    cur.execute(f"""
                    INSERT INTO {SCHEMA}.youtube_cleaned_data (
                        code, channel_id, original_artist, song_title, video_id,
                        video_title, channel_name, views, artist_found, 
                        song_title_found, video_url, upload_date, valid
                    ) VALUES (
                        %(code)s, %(channel_id)s, %(original_artist)s, %(song_title)s, %(video_id)s,
                        %(video_title)s, %(channel_name)s, %(views)s, %(artist_found)s,
                        %(song_title_found)s, %(video_url)s, %(upload_date)s, %(valid)s
                    )
                    ON CONFLICT (code) DO UPDATE SET
                        channel_id = EXCLUDED.channel_id,
                        original_artist = EXCLUDED.original_artist,
                        song_title = EXCLUDED.song_title,
                        video_id = EXCLUDED.video_id,
                        video_title = EXCLUDED.video_title,
                        channel_name = EXCLUDED.channel_name,
                        views = EXCLUDED.views,
                        artist_found = EXCLUDED.artist_found,
                        song_title_found = EXCLUDED.song_title_found,
                        video_url = EXCLUDED.video_url,
                        upload_date = EXCLUDED.upload_date,
                        valid = EXCLUDED.valid,
                        updated_at = CURRENT_TIMESTAMP
                    """, clean_data)
                
                conn.commit()
                logger.info(f"Processed code {row['code']} - Valid: {valid}")
                
            except Exception as e:
                logger.error(f"Error processing row {row.get('code')}: {str(e)}")
                conn.rollback()
        
        logger.info("Data cleaning and validation completed successfully")
        
    except Exception as e:
        logger.error(f"Processing failed: {str(e)}", exc_info=True)
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    try:
        process_data()
    except Exception as e:
        logger.critical(f"Script failed: {str(e)}", exc_info=True)
        sys.exit(1)