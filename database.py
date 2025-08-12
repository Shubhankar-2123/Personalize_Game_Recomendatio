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
        """Create necessary indexes in MongoDB collections with validation"""
        try:
            # Create indexes for users and interactions
            self.users_collection.create_index("username", unique=True)
            self.interactions_collection.create_index([("user_id", 1), ("game_id", 1)], unique=True)
            
            # Verify indexes were created
            users_indexes = self.users_collection.index_information()
            if 'username_1' not in users_indexes:
                raise Exception("Failed to create username index")
                
            interactions_indexes = self.interactions_collection.index_information()
            if 'user_id_1_game_id_1' not in interactions_indexes:
                raise Exception("Failed to create user_id+game_id index")
            
            print("✅ Successfully created and verified MongoDB indexes")
            
        except Exception as e:
            print(f"❌ Error creating indexes: {e}")
            # Try to drop and recreate indexes if there was an error
            try:
                self.users_collection.drop_index("username_1")
                self.interactions_collection.drop_index([("user_id", 1), ("game_id", 1)])
                self.users_collection.create_index("username", unique=True)
                self.interactions_collection.create_index([("user_id", 1), ("game_id", 1)], unique=True)
                print("✅ Successfully recreated indexes after error")
            except Exception as retry_error:
                print(f"❌ Critical: Failed to recreate indexes: {retry_error}")
                raise retry_error
    
    def setup_sqlite(self):
        """Set up SQLite database for games"""
        try:
            self.sqlite_conn = sqlite3.connect('data/recommendations.db', check_same_thread=False)
            cursor = self.sqlite_conn.cursor()
            
            # Create games table with id from CSV (no AUTOINCREMENT)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY,
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
            
            # Insert new games using id from CSV
            for game in games_data:
                cursor.execute('''
                    INSERT INTO games (id, URL, Name, Description, Developer,
                                    "Average User Rating", "User Rating Count",
                                    "Primary Genre", Genres, "Icon URL")
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    game.get('id'),
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
    
    def create_user(self, username, password, email=None):
        """Create a new user in MongoDB with enhanced error handling and email verification"""
        try:
            if self.users_collection is None:
                print("❌ Critical Error: users_collection is None - MongoDB connection issue")
                raise ConnectionError("MongoDB not connected")
            if not username or not password:
                raise ValueError("Username and password cannot be empty")
            user_data = {
                "username": username,
                "password": password,
                "email": email,
                "created_at": datetime.utcnow(),
                "last_updated": datetime.utcnow(),
                "verified": False
            }
            try:
                result = self.users_collection.insert_one(user_data)
                if not result.acknowledged:
                    raise Exception("MongoDB did not acknowledge the insert operation")
                print(f"✅ User created successfully with ID: {result.inserted_id}")
                return str(result.inserted_id)
            except DuplicateKeyError:
                print(f"❌ Duplicate username detected: {username}")
                raise ValueError(f"Username '{username}' already exists") from None
        except ValueError as ve:
            print(f"❌ Validation error creating user: {ve}")
            raise ve
        except Exception as e:
            print(f"❌ Database error creating user: {e}")
            raise Exception("Failed to create user due to database error") from e

    def verify_user(self, user_id):
        """Set verified=True for a user by user_id"""
        try:
            result = self.users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": {"verified": True, "last_updated": datetime.utcnow()}})
            return result.modified_count > 0
        except Exception as e:
            print(f"❌ Error verifying user: {e}")
            return False
    
    def update_user_profile(self, user_id, new_username=None, new_email=None):
        """Update user's profile information (username, email)"""
        try:
            if self.users_collection is None:
                raise ConnectionError("MongoDB not connected")
            update_fields = {}
            if new_username:
                update_fields["username"] = new_username
            if new_email:
                update_fields["email"] = new_email
            if not update_fields:
                raise ValueError("No fields to update")
            update_fields["last_updated"] = datetime.utcnow()
            result = self.users_collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": update_fields}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"❌ Error updating user profile: {e}")
            return False
    
    def get_user_by_username(self, username):
        """Get user by username from MongoDB"""
        try:
            if self.users_collection is None:
                print("DEBUG: users_collection is None")
                raise ConnectionError("MongoDB not connected")
            
            user = self.users_collection.find_one({"username": username})
            print(f"DEBUG: Searched for {username}, found: {user}")
            return user
            
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
            
            game_id = int(game[0])  # Ensure this is always an integer
            game_url = game[1]
            
            # Store rating in MongoDB
            interaction_data = {
                "user_id": str(user_id),
                "game_id": game_id,  # Always integer
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
                print(f"✅ Rating saved for user {user_id} on game '{game_name}' (game_id={game_id})")
                return True
            else:
                print(f"❌ Error: MongoDB did not acknowledge rating save for user {user_id} on game '{game_name}' (game_id={game_id})")
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
    
    def get_game_by_id(self, game_id):
        """Get game details by ID from SQLite"""
        try:
            cursor = self.sqlite_conn.cursor()
            cursor.execute('SELECT * FROM games WHERE id = ?', (game_id,))
            row = cursor.fetchone()
            if row:
                columns = [description[0] for description in cursor.description]
                game_dict = {}
                for i, value in enumerate(row):
                    game_dict[columns[i]] = value
                return game_dict
            return None
        except Exception as e:
            print(f"❌ Error getting game by id: {e}")
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
        """Get all unique genres from SQLite - combines Primary Genre and detailed genres"""
        try:
            cursor = self.sqlite_conn.cursor()
            
            # Get primary genres
            cursor.execute('SELECT DISTINCT "Primary Genre" FROM games WHERE "Primary Genre" IS NOT NULL')
            primary_genres = [row[0] for row in cursor.fetchall()]
            
            # Get detailed genres from Genres column
            cursor.execute('SELECT DISTINCT Genres FROM games WHERE Genres IS NOT NULL')
            detailed_genres_raw = [row[0] for row in cursor.fetchall()]
            
            # Parse detailed genres (they're comma-separated)
            detailed_genres = set()
            for genre_string in detailed_genres_raw:
                if genre_string:
                    # Split by comma and clean up
                    genres_list = [g.strip() for g in genre_string.split(',')]
                    detailed_genres.update(genres_list)
            
            # Combine both sets and remove duplicates
            all_genres = set(primary_genres) | detailed_genres
            
            # Filter out empty strings and sort
            all_genres = [g for g in all_genres if g and g.strip()]
            return sorted(all_genres)
            
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
        """Get games by genre from SQLite - searches both Primary Genre and Genres columns"""
        try:
            cursor = self.sqlite_conn.cursor()
            
            # Get total count - search both Primary Genre and Genres columns
            cursor.execute('''
                SELECT COUNT(*) FROM games 
                WHERE "Primary Genre" = ? OR Genres LIKE ?
            ''', (genre, f'%{genre}%'))
            total = cursor.fetchone()[0]
            
            # Get paginated results
            cursor.execute('''
                SELECT * FROM games 
                WHERE "Primary Genre" = ? OR Genres LIKE ?
                LIMIT ? OFFSET ?
            ''', (genre, f'%{genre}%', per_page, (page - 1) * per_page))
            
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
    
    def get_all_users(self):
        """Return a list of all users"""
        try:
            return list(self.users_collection.find())
        except Exception as e:
            print(f"❌ Error getting all users: {e}")
            return []

    def get_all_interactions(self):
        """Return a list of all user interactions"""
        try:
            if not self.is_connected():
                return []
            return list(self.interactions_collection.find())
        except Exception as e:
            print(f"❌ Error getting all interactions: {e}")
            return []

    # def get_all_games(self):
    #     """Return a list of all games from SQLite"""
    #     try:
    #         cursor = self.sqlite_conn.cursor()
    #         cursor.execute('SELECT * FROM games')
    #         columns = [desc[0] for desc in cursor.description]
    #         return [dict(zip(columns, row)) for row in cursor.fetchall()]
    #     except Exception as e:
    #         print(f"❌ Error getting all games: {e}")
    #         return []
    
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