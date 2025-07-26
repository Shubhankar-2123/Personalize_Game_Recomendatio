import os
from dotenv import load_dotenv
import secrets

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class Config:
    # MongoDB Configuration
    MONGODB_URI = os.getenv('MONGODB_URI')
    MONGODB_DB_NAME = os.getenv('MONGODB_DB_NAME')
    MONGODB_USERS_COLLECTION = os.getenv('MONGODB_USERS_COLLECTION')
    MONGODB_INTERACTIONS_COLLECTION = os.getenv('MONGODB_INTERACTIONS_COLLECTION')
    
    # SQLite Configuration
    SQLITE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'recommendations.db')
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'shubhankar2321')
    # DEBUG = True
    HOST = '0.0.0.0'
    PORT = 3000
    
    # Flask-Mail Configuration
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'true').lower() in ['true', '1', 'yes']
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', MAIL_USERNAME)
    
    # Game Data Configuration
    GAMES_CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'Game_processed_data.csv')
    
    # Recommendation Settings
    DEFAULT_RECOMMENDATIONS = 12
    POPULAR_GAMES_LIMIT = 12
    GAMES_PER_PAGE = 12 