import os
from dotenv import load_dotenv
import secrets

# Load environment variables
load_dotenv()

class Config:
    # MongoDB Configuration
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    MONGODB_DB_NAME = os.getenv('MONGODB_DB_NAME', 'game_recommendation')
    MONGODB_USERS_COLLECTION = os.getenv('MONGODB_USERS_COLLECTION', 'users')
    MONGODB_INTERACTIONS_COLLECTION = os.getenv('MONGODB_INTERACTIONS_COLLECTION', 'interactions')
    
    # SQLite Configuration
    SQLITE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'recommendations.db')
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
    DEBUG = True
    HOST = '0.0.0.0'
    PORT = 5000
    
    # Game Data Configuration
    GAMES_CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'Game_processed_data.csv')
    
    # Recommendation Settings
    DEFAULT_RECOMMENDATIONS = 12
    POPULAR_GAMES_LIMIT = 12
    GAMES_PER_PAGE = 12 