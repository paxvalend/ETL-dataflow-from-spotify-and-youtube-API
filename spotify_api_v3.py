import psycopg2
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import time
import access
from datetime import datetime
import logging
import sys
import pandas as pd

# ---------------- CONFIG ----------------
CLIENT_ID = access.CLIENT_ID
CLIENT_SECRET = access.CLIENT_SECRET
# PostgreSQL credentials from access module
DB_CONFIG = {
    'host': access.DB_HOST,
    'database': access.DB_NAME,
    'user': access.DB_USER,
    'password': access.DB_PASSWORD,
    'port': access.DB_PORT
}
SCHEMA = 'test_stored'  # Schema name from access.py or directly defined
SLEEP_SECONDS = 0.3  # Avoid rate limiting
# ---------------------------------------

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('spotify_metadata.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Spotify API auth
auth_manager = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
sp = spotipy.Spotify(auth_manager=auth_manager)

def get_artist_info(artist_id):
    """Get artist info including monthly listeners and genres"""
    try:
        artist = sp.artist(artist_id)
        return {
            'monthly_listeners': artist.get('followers', {}).get('total'),
            'artist_genres': ', '.join(artist.get('genres', [])) if artist.get('genres') else None
        }
    except Exception as e:
        logger.error(f"Error fetching artist info for {artist_id}: {str(e)}", exc_info=True)
        return {
            'monthly_listeners': None,
            'artist_genres': None
        }

def get_spotify_metadata(title, artist=None):
    query = title
    if artist and artist != 'None':  # Handle None values from DB
        query += f" artist:{artist}"
    
    try:
        result = sp.search(q=query, type='track', limit=1)
        items = result.get('tracks', {}).get('items', [])
        if items:
            track = items[0]
            artist_id = track['artists'][0]['id']
            artist_info = get_artist_info(artist_id)
            
            return {
                'spotify_title': track['name'],
                'spotify_artist': track['artists'][0]['name'],
                'album': track['album']['name'],
                'release_date': track['album']['release_date'],
                'isrc': track['external_ids'].get('isrc'),
                'spotify_url': track['external_urls']['spotify'],
                'duration_seconds': round(track['duration_ms'] / 1000, 2),
                'popularity': track['popularity'],
                'monthly_listeners': artist_info['monthly_listeners'],
                'artist_genres': artist_info['artist_genres']
            }
        else:
            logger.warning(f"Track not found on Spotify - Title: '{title}', Artist: '{artist}'")
    except Exception as e:
        logger.error(f"Error fetching Spotify metadata - Title: '{title}', Artist: '{artist}': {str(e)}", exc_info=True)
    
    return {
        'spotify_title': None,
        'spotify_artist': None,
        'album': None,
        'release_date': None,
        'isrc': None,
        'spotify_url': None,
        'duration_seconds': None,
        'popularity': None,
        'monthly_listeners': None,
        'artist_genres': None
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
    """Fetch songs from internal_songs table"""
    conn = None
    try:
        conn = get_db_connection()
        query = f"""
        SELECT code, original_artist, song_title 
        FROM {SCHEMA}.internal_songs
        WHERE code NOT IN (SELECT code FROM {SCHEMA}.spotify_metadata)
        """
        with conn.cursor() as cur:
            cur.execute(query)
            columns = [desc[0] for desc in cur.description]
            data = cur.fetchall()
        
        if not data:
            logger.info("No new songs found to process in database")
            return pd.DataFrame(columns=columns)
        
        logger.info(f"Found {len(data)} songs to process from database")
        return pd.DataFrame(data, columns=columns)
    except Exception as e:
        logger.error(f"Error fetching songs from database: {str(e)}", exc_info=True)
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

def save_to_db(data):
    """Save metadata to spotify_metadata table"""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            query = f"""
            INSERT INTO {SCHEMA}.spotify_metadata (
                code, isrc, original_artist, song_title, spotify_title, 
                spotify_artist, release_date, spotify_url, duration_seconds, 
                monthly_listeners, popularity, artist_genres
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (code) DO UPDATE SET
                isrc = EXCLUDED.isrc,
                spotify_title = EXCLUDED.spotify_title,
                spotify_artist = EXCLUDED.spotify_artist,
                release_date = EXCLUDED.release_date,
                spotify_url = EXCLUDED.spotify_url,
                duration_seconds = EXCLUDED.duration_seconds,
                monthly_listeners = EXCLUDED.monthly_listeners,
                popularity = EXCLUDED.popularity,
                artist_genres = EXCLUDED.artist_genres,
                updated_at = CURRENT_TIMESTAMP
            """
            
            cur.execute(query, (
                data['code'],
                data['isrc'],
                data['original_artist'],
                data['song_title'],
                data['spotify_title'],
                data['spotify_artist'],
                data['release_date'],
                data['spotify_url'],
                data['duration_seconds'],
                data['monthly_listeners'],
                data['popularity'],
                data['artist_genres']
            ))
            
            conn.commit()
            logger.info(f"Successfully saved metadata for code: {data['code']}")
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
        logger.info("Starting Spotify metadata processing")
        df = get_songs_from_db()
        
        if df.empty:
            logger.info("No new songs to process")
            return
        
        total_tracks = len(df)
        logger.info(f"Processing {total_tracks} songs...")
        
        for idx, row in df.iterrows():
            title = row['song_title']
            artist = row['original_artist']
            code = row['code']
            
            logger.info(f"Processing {idx+1}/{total_tracks}: {title} by {artist} (Code: {code})")
            
            meta = get_spotify_metadata(title, artist)
            
            # Combine with original data
            combined_data = {
                'code': code,
                'original_artist': artist,
                'song_title': title,
                **meta
            }
            
            save_to_db(combined_data)
            time.sleep(SLEEP_SECONDS)
        
        logger.info("Processing completed successfully")
    except Exception as e:
        logger.error(f"Fatal error in process_songs: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    try:
        process_songs()
    except Exception as e:
        logger.critical(f"Script failed: {str(e)}", exc_info=True)
        sys.exit(1)