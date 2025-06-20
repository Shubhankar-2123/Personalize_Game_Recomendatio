from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, ConnectionFailure, ConfigurationError
from bson import ObjectId
from datetime import datetime
import pandas as pd
from config import Config
import sqlite3
import os

class MongoDBManager:
    def __init__(self):
        self.client = None
        self.db = None
        self.users_collection = None
        self.interactions_collection = None
        self.sqlite_conn = None
        self.connected = False
        self.connect()
    
    def connect(self):
        """Connect to MongoDB for users/interactions and SQLite for games"""
        # Always set up SQLite for games data first
        try:
            self.setup_sqlite()
        except Exception as e:
            print(f"❌ Error setting up SQLite: {e}")
            raise e

        # Try connecting to MongoDB for users and interactions
        try:
            # Connect to MongoDB
            self.client = MongoClient(Config.MONGODB_URI)
            self.client.admin.command('ping')  # Test connection
            print("✅ Successfully connected to MongoDB Atlas!")
            
            # Set up MongoDB collections
            self.db = self.client[Config.MONGODB_DB_NAME]
            self.users_collection = self.db[Config.MONGODB_USERS_COLLECTION]
            self.interactions_collection = self.db[Config.MONGODB_INTERACTIONS_COLLECTION]
            
            # Create MongoDB indexes
            self.create_indexes()
            self.connected = True
            
        except Exception as e:
            print(f"⚠️  Error connecting to MongoDB: {e}")
            print("⚠️  User authentication and interactions will be disabled.")
            self.client = None
            self.db = None
            self.users_collection = None
            self.interactions_collection = None
            self.connected = False
    
    def create_indexes(self):
        """Create necessary indexes in MongoDB collections"""
        try:
            # Create indexes for users and interactions
            self.users_collection.create_index("username", unique=True)
            self.users_collection.create_index("email", unique=True)
            self.interactions_collection.create_index([("user_id", 1), ("game_id", 1)], unique=True)
            
            print("✅ Successfully created MongoDB indexes")
            
        except Exception as e:
            print(f"⚠️  Error creating indexes: {e}")
    
    def setup_sqlite(self):
        """Set up SQLite database for games"""
        try:
            self.sqlite_conn = sqlite3.connect('data/recommendations.db', check_same_thread=False)
            cursor = self.sqlite_conn.cursor()
            
            # Create games table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    URL TEXT,
                    Name TEXT UNIQUE NOT NULL,
                    Description TEXT,
                    Developer TEXT,
                    "Average User Rating" REAL,
                    "User Rating Count" INTEGER,
                    "Primary Genre" TEXT,
                    Genres TEXT,
                    "Icon URL" TEXT
                )
            ''')
            
            self.sqlite_conn.commit()
            print("✅ Successfully set up SQLite database")
            
        except Exception as e:
            print(f"❌ Error setting up SQLite database: {e}")
            raise e
    
    def load_games_from_csv(self, csv_path):
        """Load games data from CSV file into SQLite"""
        try:
            # Read CSV file
            df = pd.read_csv(csv_path)
            # Remove duplicates based on Name
            df = df.drop_duplicates(subset=['Name'], keep='first')
            games_data = df.to_dict('records')
            
            cursor = self.sqlite_conn.cursor()
            # Clear existing games
            cursor.execute('DELETE FROM games')
            
            # Insert new games
            for game in games_data:
                cursor.execute('''
                    INSERT INTO games (URL, Name, Description, Developer,
                                    "Average User Rating", "User Rating Count",
                                    "Primary Genre", Genres, "Icon URL")
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    game.get('URL'),
                    game.get('Name'),
                    game.get('Description'),
                    game.get('Developer'),
                    game.get('Average User Rating'),
                    game.get('User Rating Count'),
                    game.get('Primary Genre'),
                    game.get('Genres'),
                    game.get('Icon URL')
                ))
            
            self.sqlite_conn.commit()
            print(f"✅ Successfully loaded {len(games_data)} games into SQLite")
            
        except Exception as e:
            print(f"❌ Error loading games data: {e}")
            raise e
    
    def create_user(self, username, password):
        """Create a new user in MongoDB"""
        try:
            if self.users_collection is None:
                raise ConnectionError("MongoDB not connected")
            
            user_data = {
                "username": username,
                "password": password,
                "created_at": datetime.utcnow()
            }
            
            result = self.users_collection.insert_one(user_data)
            return str(result.inserted_id)
            
        except DuplicateKeyError:
            print(f"❌ Error: Username {username} already exists")
            return None
        except Exception as e:
            print(f"❌ Error creating user: {e}")
            return None
    
    def get_user_by_username(self, username):
        """Get user by username from MongoDB"""
        try:
            if self.users_collection is None:
                raise ConnectionError("MongoDB not connected")
            
            return self.users_collection.find_one({"username": username})
            
        except Exception as e:
            print(f"❌ Error getting user: {e}")
            return None
    
    def add_rating(self, user_id, game_name, rating):
        """Add or update a game rating"""
        try:
            if not self.connected or self.interactions_collection is None:
                print("❌ Error: MongoDB not connected or interactions collection missing")
                raise ConnectionError("MongoDB not connected")
            
            # Get game from SQLite
            cursor = self.sqlite_conn.cursor()
            cursor.execute('SELECT id, URL FROM games WHERE Name = ?', (game_name,))
            game = cursor.fetchone()
            if not game:
                print(f"❌ Error: Game '{game_name}' not found in SQLite")
                raise ValueError("Game not found")
            
            game_id = game[0]
            game_url = game[1]
            
            # Store rating in MongoDB
            interaction_data = {
                "user_id": str(user_id),
                "game_id": game_id,
                "game_url": game_url,
                "value": rating,
                "timestamp": datetime.utcnow()
            }
            
            result = self.interactions_collection.update_one(
                {"user_id": str(user_id), "game_id": game_id},
                {"$set": interaction_data},
                upsert=True
            )
            if result.acknowledged:
                print(f"✅ Rating saved for user {user_id} on game '{game_name}'")
                return True
            else:
                print(f"❌ Error: MongoDB did not acknowledge rating save for user {user_id} on game '{game_name}'")
                return False
        except Exception as e:
            print(f"❌ Error adding rating: {e}")
            return False
    
    def get_user_ratings(self, user_id):
        """Get all ratings for a user from MongoDB"""
        try:
            if not self.connected:
                raise ConnectionError("MongoDB not connected")
            
            return list(self.interactions_collection.find({"user_id": str(user_id)}))
        except Exception as e:
            print(f"❌ Error getting user ratings: {e}")
            return []
    
    def get_game_by_name(self, game_name):
        """Get game details by name from SQLite"""
        try:
            cursor = self.sqlite_conn.cursor()
            cursor.execute('SELECT * FROM games WHERE Name = ?', (game_name,))
            row = cursor.fetchone()
            if row:
                columns = [description[0] for description in cursor.description]
                game_dict = {}
                for i, value in enumerate(row):
                    game_dict[columns[i]] = value
                return game_dict
            return None
        except Exception as e:
            print(f"❌ Error getting game by name: {e}")
            return None
    
    def get_game_by_url(self, game_url):
        """Get game details by URL from SQLite"""
        try:
            cursor = self.sqlite_conn.cursor()
            cursor.execute('SELECT * FROM games WHERE URL = ?', (game_url,))
            row = cursor.fetchone()
            if row:
                columns = [description[0] for description in cursor.description]
                game_dict = {}
                for i, value in enumerate(row):
                    game_dict[columns[i]] = value
                return game_dict
            return None
        except Exception as e:
            print(f"❌ Error getting game by URL: {e}")
            return None
    
    def get_all_games(self, limit=None):
        """Get all games from SQLite"""
        try:
            cursor = self.sqlite_conn.cursor()
            if limit:
                cursor.execute('SELECT * FROM games LIMIT ?', (limit,))
            else:
                cursor.execute('SELECT * FROM games')
            
            columns = [description[0] for description in cursor.description]
            games = []
            for row in cursor.fetchall():
                game_dict = {}
                for i, value in enumerate(row):
                    game_dict[columns[i]] = value
                games.append(game_dict)
            return games
        except Exception as e:
            print(f"❌ Error getting all games: {e}")
            return []
    
    def get_popular_games(self, limit=12):
        """Get popular games from SQLite"""
        try:
            cursor = self.sqlite_conn.cursor()
            cursor.execute('''
                SELECT * FROM games 
                ORDER BY "User Rating Count" DESC 
                LIMIT ?
            ''', (limit,))
            
            columns = [description[0] for description in cursor.description]
            games = []
            for row in cursor.fetchall():
                game_dict = {}
                for i, value in enumerate(row):
                    game_dict[columns[i]] = value
                games.append(game_dict)
            return games
        except Exception as e:
            print(f"❌ Error getting popular games: {e}")
            return []
    
    def get_all_genres(self):
        """Get all unique genres from SQLite"""
        try:
            cursor = self.sqlite_conn.cursor()
            cursor.execute('SELECT DISTINCT "Primary Genre" FROM games WHERE "Primary Genre" IS NOT NULL')
            genres = [row[0] for row in cursor.fetchall()]
            return sorted(genres)
        except Exception as e:
            print(f"❌ Error getting genres: {e}")
            return []
    
    def search_games(self, query, page=1, per_page=12):
        """Search games in SQLite"""
        try:
            cursor = self.sqlite_conn.cursor()
            search_term = f"%{query}%"
            
            # Get total count
            cursor.execute('''
                SELECT COUNT(*) FROM games 
                WHERE Name LIKE ? OR Developer LIKE ? OR "Primary Genre" LIKE ? OR Genres LIKE ?
            ''', (search_term, search_term, search_term, search_term))
            total = cursor.fetchone()[0]
            
            # Get paginated results
            cursor.execute('''
                SELECT * FROM games 
                WHERE Name LIKE ? OR Developer LIKE ? OR "Primary Genre" LIKE ? OR Genres LIKE ?
                LIMIT ? OFFSET ?
            ''', (search_term, search_term, search_term, search_term, per_page, (page - 1) * per_page))
            
            columns = [description[0] for description in cursor.description]
            games = []
            for row in cursor.fetchall():
                game_dict = {}
                for i, value in enumerate(row):
                    game_dict[columns[i]] = value
                games.append(game_dict)
            return games, total
        except Exception as e:
            print(f"❌ Error searching games: {e}")
            return [], 0
    
    def get_games_by_genre(self, genre, page=1, per_page=12):
        """Get games by genre from SQLite"""
        try:
            cursor = self.sqlite_conn.cursor()
            
            # Get total count
            cursor.execute('SELECT COUNT(*) FROM games WHERE "Primary Genre" = ?', (genre,))
            total = cursor.fetchone()[0]
            
            # Get paginated results
            cursor.execute('''
                SELECT * FROM games 
                WHERE "Primary Genre" = ?
                LIMIT ? OFFSET ?
            ''', (genre, per_page, (page - 1) * per_page))
            
            columns = [description[0] for description in cursor.description]
            games = []
            for row in cursor.fetchall():
                game_dict = {}
                for i, value in enumerate(row):
                    game_dict[columns[i]] = value
                games.append(game_dict)
            return games, total
        except Exception as e:
            print(f"❌ Error getting games by genre: {e}")
            return [], 0
    
    def is_connected(self):
        """Check if MongoDB is connected"""
        return self.connected
    
    def close(self):
        """Close database connections"""
        if self.client:
            self.client.close()
        if self.sqlite_conn:
            self.sqlite_conn.close()

# Initialize the database manager
db_manager = MongoDBManager()

# Remove the unnecessary database listing code
# print(client.list_database_names()) 