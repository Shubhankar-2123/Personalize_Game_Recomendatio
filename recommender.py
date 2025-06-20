import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
from collections import defaultdict
import os
from scipy.sparse import csr_matrix
from database import db_manager

class GameRecommender:
    def __init__(self, max_games=5000):
        """Initialize recommender system"""
        try:
            # Load games from database
            self.games_data = db_manager.get_all_games(max_games)
            
            if not self.games_data:
                print("⚠️  No games found in database. Please load games data first.")
                self.games_df = None
                self.game_id_to_idx = {}
                self.idx_to_game_id = {}
                self.similarity_batches = []
                return
            
            # Convert to DataFrame for processing
            self.games_df = pd.DataFrame(self.games_data)
            
            # Validate required columns
            required_columns = {
                'URL', 'Name', 'Icon URL', 'Average User Rating',
                'User Rating Count', 'Description', 'Developer',
                'Primary Genre', 'Genres'
            }
            missing_cols = required_columns - set(self.games_df.columns)
            if missing_cols:
                raise ValueError(f"Missing columns: {missing_cols}")
            
            self._create_mappings()
            self.prepare_data()
            self.build_similarity_matrix()
            
            print(f"✅ GameRecommender initialized with {len(self.games_df)} games")
            
        except Exception as e:
            print(f"❌ Failed to initialize GameRecommender: {e}")
            self.games_df = None
            self.games_data = []
            self.game_id_to_idx = {}
            self.idx_to_game_id = {}
            self.similarity_batches = []

    def _create_mappings(self):
        """Create memory-efficient mappings"""
        if self.games_df is None:
            return
            
        self.games_df = self.games_df.drop_duplicates(subset=['URL'])
        self.game_id_to_idx = {
            game_id: idx for idx, game_id in enumerate(self.games_df['URL'])
        }
        self.idx_to_game_id = {
            idx: game_id for game_id, idx in self.game_id_to_idx.items()
        }

    def prepare_data(self):
        """Clean data with memory efficiency"""
        if self.games_df is None:
            return
            
        text_cols = ['Description', 'Primary Genre', 'Genres', 'Developer']
        for col in text_cols:
            if col in self.games_df.columns:
                self.games_df[col] = self.games_df[col].fillna('').astype(str)
        
        self.games_df['combined_features'] = (
            self.games_df['Primary Genre'] + ' ' + 
            self.games_df['Genres'] + ' ' + 
            self.games_df['Description'].str[:500] + ' ' +  # Limit description size
            self.games_df['Developer']
        )

    def build_similarity_matrix(self):
        """Build memory-efficient similarity matrix"""
        if self.games_df is None:
            return
            
        tfidf = TfidfVectorizer(
            stop_words='english',
            max_features=2000,  # Reduced features
            ngram_range=(1, 1)  # Only unigrams
        )
        
        # Use sparse matrices
        tfidf_matrix = tfidf.fit_transform(self.games_df['combined_features'])
        
        # Calculate similarity in batches
        self.similarity_batches = []
        batch_size = 1000
        for i in range(0, tfidf_matrix.shape[0], batch_size):
            batch = tfidf_matrix[i:i+batch_size]
            sim_batch = cosine_similarity(batch, tfidf_matrix)
            self.similarity_batches.append(csr_matrix(sim_batch))  # Keep sparse

    def _get_similarity_row(self, idx):
        """Get similarity row from batches"""
        if not self.similarity_batches:
            return None
            
        batch_idx = idx // 1000
        row_in_batch = idx % 1000
        return self.similarity_batches[batch_idx].getrow(row_in_batch).toarray()[0]

    def get_recommendations(self, user_id, top_n=10):
        """Get personalized recommendations"""
        try:
            # Check if we have games data
            if self.games_df is None:
                print("⚠️  No games data available. Using fallback recommendations.")
                return self.get_popular_games(top_n)
            
            # Get user ratings from database
            user_ratings = db_manager.get_user_ratings(user_id)
            
            if not user_ratings:
                return self.get_popular_games(top_n)
            
            # Build user profile using batches
            user_profile = np.zeros(len(self.games_df))
            valid_ratings = 0
            
            for rating in user_ratings:
                game_url = rating['game_url']
                rating_value = rating['value']
                
                if game_url in self.game_id_to_idx:
                    idx = self.game_id_to_idx[game_url]
                    similarity_row = self._get_similarity_row(idx)
                    if similarity_row is not None:
                        user_profile += similarity_row * rating_value
                        valid_ratings += 1
            
            if valid_ratings == 0:
                return self.get_popular_games(top_n)
            
            # Normalize user profile
            user_profile /= valid_ratings
            
            # Get top similar games
            sim_scores = list(enumerate(user_profile))
            sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)
            
            # Filter out games user has already rated
            rated_game_urls = {rating['game_url'] for rating in user_ratings}
            recommendations = []
            
            for idx, score in sim_scores:
                game_url = self.games_df.iloc[idx]['URL']
                if game_url not in rated_game_urls:
                    recommendations.append((idx, score))
                if len(recommendations) >= top_n:
                    break
            
            # Get game details for recommendations
            if recommendations:
                recommended_indices = [idx for idx, _ in recommendations]
                recommended_games = self.games_df.iloc[recommended_indices]
                return recommended_games.to_dict('records')
            else:
                return self.get_popular_games(top_n)
                
        except Exception as e:
            print(f"Error getting recommendations: {e}")
            return self.get_popular_games(top_n)

    def get_popular_games(self, top_n=10):
        """Get popular games from database"""
        try:
            popular_games = db_manager.get_popular_games(top_n)
            if popular_games:
                return popular_games
            
            # Fallback to DataFrame if database query fails
            if self.games_df is not None:
                popular = self.games_df[
                    (self.games_df['User Rating Count'] > 10) & 
                    (self.games_df['Average User Rating'] >= 3.5)
                ].sort_values(
                    by=['User Rating Count', 'Average User Rating'],
                    ascending=False
                ).head(top_n)
                
                return popular.to_dict('records')
            else:
                print("⚠️  No games data available for recommendations.")
                return []
                
        except Exception as e:
            print(f"Error getting popular games: {e}")
            return []

    def get_game_details(self, game_url):
        """Get game details by URL"""
        try:
            # Try getting from database first
            game = db_manager.get_game_by_url(game_url)
            if game:
                return game
            
            # Fallback to DataFrame
            if self.games_df is not None:
                game = self.games_df[self.games_df['URL'] == game_url]
                if not game.empty:
                    return game.iloc[0].to_dict()
            
            return None
        except Exception as e:
            print(f"Error getting game details: {e}")
            return None

    def get_game_by_name(self, game_name):
        """Get game details by name"""
        try:
            # Try getting from database first
            game = db_manager.get_game_by_name(game_name)
            if game:
                return game
            
            # Fallback to DataFrame
            if self.games_df is not None:
                game = self.games_df[
                    self.games_df['Name'].str.lower() == game_name.lower()
                ]
                if not game.empty:
                    return game.iloc[0].to_dict()
            
            return None
        except Exception as e:
            print(f"Error getting game by name: {e}")
            return None
    def get_game_by_url(self, game_url):
        """Get game details by URL"""
        try:
            # Try getting from database first
            game = db_manager.get_game_by_url(game_url)
            if game:
                return game

            # Fallback to DataFrame
            if self.games_df is not None:
                game = self.games_df[self.games_df['URL'] == game_url]
                if not game.empty:
                    return game.iloc[0].to_dict()

            return None
        except Exception as e:
            print(f"Error getting game by URL: {e}")
            return None
    def record_interaction(self, user_id, game_url, interaction_type, value=None):
        """Record user interaction with a game"""
        try:
            if interaction_type == 'rating' and value is not None:
                # Get game by URL
                game = self.get_game_by_url(game_url)
                if not game:
                    return False
                
                # Record rating in database
                db_manager.add_rating(user_id, game['Name'], value)
                return True
            return False
        except Exception as e:
            print(f"Error recording interaction: {e}")
            return False