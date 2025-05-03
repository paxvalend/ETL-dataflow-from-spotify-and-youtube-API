import psycopg2
import requests
import time
import access
import logging
import sys
from datetime import datetime

# ---------------- CONFIG ----------------
YOUTUBE_API_KEY = access.YOUTUBE_API_KEY
SCHEMA = 'test_stored'  # Schema name from access.py or directly defined
SLEEP_SECONDS = 0.3  # Avoid rate limiting
# ---------------------------------------

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('youtube_metadata.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Database configuration from access module
DB_CONFIG = {
    'host': access.DB_HOST,
    'database': access.DB_NAME,
    'user': access.DB_USER,
    'password': access.DB_PASSWORD,
    'port': access.DB_PORT
}

def get_video_details(video_id):
    """Get additional video details from YouTube API"""
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,statistics",
        "id": video_id,
        "key": YOUTUBE_API_KEY
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get("items"):
            item = data["items"][0]
            return {
                'channel_name': item['snippet'].get('channelTitle'),
                'views': item['statistics'].get('viewCount'),
                'upload_date': item['snippet'].get('publishedAt'),
                'video_url': f"https://www.youtube.com/watch?v={video_id}"
            }
    except Exception as e:
        logger.error(f"Error fetching video details for {video_id}: {str(e)}", exc_info=True)
    
    return {
        'channel_name': None,
        'views': None,
        'upload_date': None,
        'video_url': None
    }

def get_youtube_metadata(title, artist=None):
    query = title
    if artist and artist != 'None':
        query += f" {artist}"
    
    logger.info(f"Searching YouTube for: {query}")
    
    search_url = "https://www.googleapis.com/youtube/v3/search"
    search_params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": 1,
        "key": YOUTUBE_API_KEY
    }
    
    try:
        search_response = requests.get(search_url, params=search_params)
        search_response.raise_for_status()
        search_data = search_response.json()
        
        if search_data.get("items"):
            item = search_data["items"][0]
            video_id = item["id"]["videoId"]
            
            # Get additional video details
            video_details = get_video_details(video_id)
            
            return {
                'video_id': video_id,
                'channel_id': item['snippet'].get('channelId'),
                'video_title': item['snippet'].get('title'),
                'artist_found': artist if artist else None,
                'song_title_found': title,
                **video_details
            }
        else:
            logger.warning(f"Video not found on YouTube - Title: '{title}', Artist: '{artist}'")
    except Exception as e:
        logger.error(f"Error fetching YouTube metadata - Title: '{title}', Artist: '{artist}': {str(e)}", exc_info=True)
    
    return {
        'video_id': None,
        'channel_id': None,
        'video_title': None,
        'artist_found': None,
        'song_title_found': None,
        'channel_name': None,
        'views': None,
        'upload_date': None,
        'video_url': None
    }

def get_db_connection():
    """Establish database connection with schema in search_path"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(f"SET search_path TO {SCHEMA}, public;")
        logger.info("Database connection established successfully")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {str(e)}", exc_info=True)
        raise

def get_songs_from_db():
    """Fetch songs from internal_songs table that need YouTube processing"""
    conn = None
    try:
        conn = get_db_connection()
        query = f"""
        SELECT code, original_artist, song_title 
        FROM {SCHEMA}.internal_songs
        WHERE code NOT IN (SELECT code FROM {SCHEMA}.youtube_metadata)
        """
        with conn.cursor() as cur:
            cur.execute(query)
            columns = [desc[0] for desc in cur.description]
            data = cur.fetchall()
        
        if not data:
            logger.info("No new songs found to process in database")
            return []
        
        logger.info(f"Found {len(data)} songs to process from database")
        return [dict(zip(columns, row)) for row in data]
    except Exception as e:
        logger.error(f"Error fetching songs from database: {str(e)}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()

def save_to_db(data):
    """Save metadata to youtube_metadata table"""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            query = f"""
            INSERT INTO {SCHEMA}.youtube_metadata (
                code, original_artist, song_title, video_id, channel_id,
                video_title, artist_found, song_title_found, channel_name,
                views, upload_date, video_url
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (code) DO UPDATE SET
                video_id = EXCLUDED.video_id,
                channel_id = EXCLUDED.channel_id,
                video_title = EXCLUDED.video_title,
                artist_found = EXCLUDED.artist_found,
                song_title_found = EXCLUDED.song_title_found,
                channel_name = EXCLUDED.channel_name,
                views = EXCLUDED.views,
                upload_date = EXCLUDED.upload_date,
                video_url = EXCLUDED.video_url,
                updated_at = CURRENT_TIMESTAMP
            """
            
            cur.execute(query, (
                data['code'],
                data['original_artist'],
                data['song_title'],
                data['video_id'],
                data['channel_id'],
                data['video_title'],
                data['artist_found'],
                data['song_title_found'],
                data['channel_name'],
                data['views'],
                data['upload_date'],
                data['video_url']
            ))
            
            conn.commit()
            logger.info(f"Successfully saved YouTube metadata for code: {data['code']}")
    except Exception as e:
        logger.error(f"Error saving to database - Code: {data.get('code')}: {str(e)}", exc_info=True)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def process_songs():
    """Main function to process all songs"""
    try:
        logger.info("Starting YouTube metadata processing")
        songs = get_songs_from_db()
        
        if not songs:
            logger.info("No new songs to process")
            return
        
        total_tracks = len(songs)
        logger.info(f"Processing {total_tracks} songs...")
        
        for idx, song in enumerate(songs):
            title = song['song_title']
            artist = song['original_artist']
            code = song['code']
            
            logger.info(f"Processing {idx+1}/{total_tracks}: {title} by {artist} (Code: {code})")
            
            meta = get_youtube_metadata(title, artist)
            
            # Combine with original data
            combined_data = {
                'code': code,
                'original_artist': artist,
                'song_title': title,
                **meta
            }
            
            save_to_db(combined_data)
            time.sleep(SLEEP_SECONDS)
        
        logger.info("YouTube metadata processing completed successfully")
    except Exception as e:
        logger.error(f"Fatal error in process_songs: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    try:
        process_songs()
    except Exception as e:
        logger.critical(f"Script failed: {str(e)}", exc_info=True)
        sys.exit(1)