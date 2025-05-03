import psycopg2
import pandas as pd
from datetime import datetime
import access
import logging
import sys
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('clean_songs_data.log'),
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

def create_clean_table(conn):
    """Create the clean_songs_data table if not exists"""
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA}.clean_songs_data (
                song_id SERIAL PRIMARY KEY,
                code VARCHAR(255) NOT NULL,
                original_artist VARCHAR(255),
                song_title VARCHAR(255),
                standardized_title VARCHAR(255),
                standardized_artist VARCHAR(255),
                isrc VARCHAR(15),
                spotify_title VARCHAR(255),
                spotify_artist VARCHAR(255),
                album VARCHAR(255),
                release_date DATE,
                spotify_url TEXT,
                duration_seconds INTEGER,
                monthly_listeners INTEGER,
                popularity INTEGER,
                youtube_video_id VARCHAR(255),
                youtube_title TEXT,
                channel_name VARCHAR(255),
                views BIGINT,
                video_url TEXT,
                upload_date DATE,
                best_source VARCHAR(10),
                data_quality_score INTEGER,
                last_verified_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.commit()
            logger.info("Clean songs table created/verified")
    except Exception as e:
        logger.error(f"Error creating clean table: {str(e)}")
        conn.rollback()
        raise

def standardize_text(text):
    """Standardize text by removing extra spaces and special formatting"""
    if not text or pd.isna(text):
        return None
    text = str(text).strip()
    text = re.sub(r'\s+', ' ', text)  # Replace multiple spaces with single space
    return text if text else None

def calculate_quality_score(row):
    """Calculate data quality score (0-100) based on available data"""
    score = 0
    
    # Basic info (30 points)
    if row['original_artist'] and row['song_title']:
        score += 30
    
    # Spotify data (30 points)
    if row['spotify_title'] and row['spotify_artist']:
        score += 30
        if row['isrc']:
            score += 10
    
    # YouTube data (30 points)
    if row['youtube_video_id'] and row['youtube_title']:
        score += 30
    
    # Additional points for complete data
    if row['release_date'] and row['duration_seconds']:
        score += 5
    if row['monthly_listeners'] is not None:
        score += 5
    if row['popularity'] is not None:
        score += 5
    if row['views'] is not None:
        score += 5
    
    return min(100, score)  # Cap at 100

def determine_best_source(row):
    """Determine the best source based on available data"""
    has_spotify = row['spotify_title'] is not None
    has_youtube = row['youtube_video_id'] is not None
    
    if has_spotify and has_youtube:
        return 'both'
    elif has_spotify:
        return 'spotify'
    elif has_youtube:
        return 'youtube'
    else:
        return 'none'

def process_data():
    """Main processing function to consolidate data"""
    conn = None
    try:
        conn = get_db_connection()
        create_clean_table(conn)
        
        # Query to join all three tables
        query = f"""
        SELECT 
            i.code,
            i.original_artist,
            i.song_title,
            s.isrc,
            s.spotify_title,
            s.spotify_artist,
            s.album,
            s.release_date,
            s.spotify_url,
            s.duration_seconds,
            s.monthly_listeners,
            s.popularity,
            y.video_id as youtube_video_id,
            y.video_title as youtube_title,
            y.channel_name,
            y.views,
            y.video_url,
            y.upload_date
        FROM {SCHEMA}.internal_songs i
        LEFT JOIN {SCHEMA}.spotify_metadata s ON i.code = s.code
        LEFT JOIN {SCHEMA}.youtube_cleaned_data y ON i.code = y.code AND y.valid = true
        """
        
        # Execute query and get data
        with conn.cursor() as cur:
            cur.execute(query)
            columns = [desc[0] for desc in cur.description]
            data = cur.fetchall()
        
        if not data:
            logger.info("No data found to process")
            return
        
        df = pd.DataFrame(data, columns=columns)
        logger.info(f"Processing {len(df)} records")
        
        # Process each record
        for _, row in df.iterrows():
            try:
                # Standardize fields
                standardized_title = standardize_text(row['song_title'])
                standardized_artist = standardize_text(row['original_artist'])
                
                # Convert numeric fields
                try:
                    monthly_listeners = int(row['monthly_listeners']) if row['monthly_listeners'] else None
                except:
                    monthly_listeners = None
                
                try:
                    views = int(row['views']) if row['views'] else None
                except:
                    views = None
                
                # Prepare data for insertion
                clean_data = {
                    'code': row['code'],
                    'original_artist': standardized_artist,
                    'song_title': standardized_title,
                    'standardized_title': standardized_title,
                    'standardized_artist': standardized_artist,
                    'isrc': row['isrc'],
                    'spotify_title': standardize_text(row['spotify_title']),
                    'spotify_artist': standardize_text(row['spotify_artist']),
                    'album': standardize_text(row['album']),
                    'release_date': row['release_date'],
                    'spotify_url': row['spotify_url'],
                    'duration_seconds': row['duration_seconds'],
                    'monthly_listeners': monthly_listeners,
                    'popularity': row['popularity'],
                    'youtube_video_id': row['youtube_video_id'],
                    'youtube_title': standardize_text(row['youtube_title']),
                    'channel_name': standardize_text(row['channel_name']),
                    'views': views,
                    'video_url': row['video_url'],
                    'upload_date': row['upload_date'],
                    'last_verified_at': datetime.now()
                }
                
                # Calculate derived fields
                clean_data['data_quality_score'] = calculate_quality_score(clean_data)
                clean_data['best_source'] = determine_best_source(clean_data)
                
                # Insert or update in clean table
                with conn.cursor() as cur:
                    # Using ON CONFLICT to update if code exists
                    cur.execute(f"""
                    INSERT INTO {SCHEMA}.clean_songs_data (
                        code, original_artist, song_title, standardized_title, standardized_artist,
                        isrc, spotify_title, spotify_artist, album, release_date,
                        spotify_url, duration_seconds, monthly_listeners, popularity,
                        youtube_video_id, youtube_title, channel_name, views, video_url,
                        upload_date, best_source, data_quality_score, last_verified_at
                    ) VALUES (
                        %(code)s, %(original_artist)s, %(song_title)s, %(standardized_title)s, %(standardized_artist)s,
                        %(isrc)s, %(spotify_title)s, %(spotify_artist)s, %(album)s, %(release_date)s,
                        %(spotify_url)s, %(duration_seconds)s, %(monthly_listeners)s, %(popularity)s,
                        %(youtube_video_id)s, %(youtube_title)s, %(channel_name)s, %(views)s, %(video_url)s,
                        %(upload_date)s, %(best_source)s, %(data_quality_score)s, %(last_verified_at)s
                    )
                    ON CONFLICT (code) DO UPDATE SET
                        original_artist = EXCLUDED.original_artist,
                        song_title = EXCLUDED.song_title,
                        standardized_title = EXCLUDED.standardized_title,
                        standardized_artist = EXCLUDED.standardized_artist,
                        isrc = EXCLUDED.isrc,
                        spotify_title = EXCLUDED.spotify_title,
                        spotify_artist = EXCLUDED.spotify_artist,
                        album = EXCLUDED.album,
                        release_date = EXCLUDED.release_date,
                        spotify_url = EXCLUDED.spotify_url,
                        duration_seconds = EXCLUDED.duration_seconds,
                        monthly_listeners = EXCLUDED.monthly_listeners,
                        popularity = EXCLUDED.popularity,
                        youtube_video_id = EXCLUDED.youtube_video_id,
                        youtube_title = EXCLUDED.youtube_title,
                        channel_name = EXCLUDED.channel_name,
                        views = EXCLUDED.views,
                        video_url = EXCLUDED.video_url,
                        upload_date = EXCLUDED.upload_date,
                        best_source = EXCLUDED.best_source,
                        data_quality_score = EXCLUDED.data_quality_score,
                        last_verified_at = EXCLUDED.last_verified_at,
                        updated_at = CURRENT_TIMESTAMP
                    """, clean_data)
                
                conn.commit()
                logger.info(f"Processed code {row['code']}")
                
            except Exception as e:
                logger.error(f"Error processing row {row.get('code')}: {str(e)}")
                conn.rollback()
        
        logger.info("Data consolidation completed successfully")
        
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