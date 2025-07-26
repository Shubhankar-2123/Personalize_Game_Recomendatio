import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
from collections import defaultdict
import os
from scipy.sparse import csr_matrix
from database import db_manager
from datetime import datetime


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
        """Get recommendations using content-filtered collaborative filtering"""
        try:
            # Check data availability
            if self.games_df is None:
                print("⚠️  No games data available. Using fallback recommendations.")
                return self.get_popular_games(top_n)
            
            user_ratings = db_manager.get_user_ratings(user_id)
            if not user_ratings:
                return self.get_popular_games(top_n)
            
            # Step 1: Get content-based candidates
            print(f"🎯 Step 1: Generating content-based candidate pool for user {user_id}")
            content_candidates = self._get_content_based_candidates(user_id, top_n * 3)
            
            if not content_candidates:
                print("⚠️  No content-based candidates found. Using popular games.")
                return self.get_popular_games(top_n)
            
            print(f"✅ Generated {len(content_candidates)} content-based candidates")
            
            # Step 2: Get collaborative scores for candidates
            print(f"🎯 Step 2: Getting collaborative filtering scores for candidates")
            collaborative_scores = self._get_collaborative_scores_for_candidates(user_id, content_candidates)
            
            if not collaborative_scores:
                print("⚠️  No collaborative scores available. Using content-based only.")
                return content_candidates[:top_n]
            
            print(f"✅ Got collaborative scores for {len(collaborative_scores)} candidates")
            
            # Step 3: Combine scores and return top recommendations
            print(f"🎯 Step 3: Combining content and collaborative scores")
            final_recommendations = self._combine_content_collaborative_scores(
                content_candidates, collaborative_scores, top_n
            )
            
            print(f"✅ Content-filtered collaborative recommendations: {len(final_recommendations)} games")
            return final_recommendations
            
        except Exception as e:
            print(f"Error in content-filtered collaborative recommendations: {e}")
            return self._get_content_based_recommendations(user_id, top_n)

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
                # Ensure 'id' is included
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
    def get_game_by_id(self, game_id):
        """Get game details by ID"""
        try:
            game = db_manager.get_game_by_id(game_id)
            if game:
                return game
            if self.games_df is not None:
                game = self.games_df[self.games_df['id'] == game_id]
                if not game.empty:
                    return game.iloc[0].to_dict()
            return None
        except Exception as e:
            print(f"Error getting game by id: {e}")
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

    def _get_user_similarity_matrix(self):
        """Calculate user similarity matrix for collaborative filtering"""
        try:
            if not db_manager.is_connected():
                return None
            
            # Get all user interactions
            all_interactions = db_manager.get_all_interactions()
            if not all_interactions:
                return None
            
            # Convert to DataFrame
            interactions_df = pd.DataFrame(all_interactions)
            
            # Create user-game rating matrix
            user_game_matrix = interactions_df.pivot_table(
                index='user_id', 
                columns='game_url', 
                values='value', 
                fill_value=0
            )
            
            # Calculate user similarity using cosine similarity
            user_similarity = cosine_similarity(user_game_matrix)
            
            # Create user similarity DataFrame
            user_similarity_df = pd.DataFrame(
                user_similarity,
                index=user_game_matrix.index,
                columns=user_game_matrix.index
            )
            
            return user_similarity_df, user_game_matrix
            
        except Exception as e:
            print(f"Error calculating user similarity: {e}")
            return None



    def _get_content_based_recommendations(self, user_id, top_n=10):
        """Get content-based filtering recommendations"""
        try:
            user_ratings = db_manager.get_user_ratings(user_id)
            if not user_ratings:
                return []
            
            # Build user profile
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
                return []
            
            user_profile /= valid_ratings  # Normalize
            
            # Get top similar games
            sim_scores = list(enumerate(user_profile))
            sim_scores.sort(key=lambda x: x[1], reverse=True)
            
            # Filter out rated games
            rated_game_urls = {rating['game_url'] for rating in user_ratings}
            content_recs = []
            
            for idx, score in sim_scores:
                game_url = self.games_df.iloc[idx]['URL']
                if game_url not in rated_game_urls:
                    game = self.games_df.iloc[idx].to_dict()
                    game['content_score'] = score
                    content_recs.append(game)
                if len(content_recs) >= top_n:
                    break
            
            return content_recs
            
        except Exception as e:
            print(f"Error getting content-based recommendations: {e}")
            return []





    def _get_content_based_candidates(self, user_id, candidate_pool_size=30):
        """Generate a pool of candidate games using content-based filtering"""
        try:
            # Get user ratings
            user_ratings = db_manager.get_user_ratings(user_id)
            
            if not user_ratings:
                return []
            
            # Build user profile using content similarity
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
                return []
            
            # Normalize user profile
            user_profile /= valid_ratings
            
            # Get top similar games (larger pool for candidates)
            sim_scores = list(enumerate(user_profile))
            sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)
            
            # Filter out games user has already rated
            rated_game_urls = {rating['game_url'] for rating in user_ratings}
            candidates = []
            
            for idx, content_score in sim_scores:
                game_url = self.games_df.iloc[idx]['URL']
                if game_url not in rated_game_urls:
                    game = self.games_df.iloc[idx].to_dict()
                    game['content_score'] = content_score
                    candidates.append(game)
                if len(candidates) >= candidate_pool_size:
                    break
            
            return candidates
            
        except Exception as e:
            print(f"Error getting content-based candidates: {e}")
            return []

    def _get_collaborative_scores_for_candidates(self, user_id, candidates):
        """Get collaborative filtering scores for the candidate games"""
        try:
            # Get user similarity matrix
            similarity_result = self._get_user_similarity_matrix()
            if similarity_result is None:
                return {}
            
            user_similarity_df, user_game_matrix = similarity_result
            
            if user_id not in user_similarity_df.index:
                return {}
            
            # Get user's similarity scores with other users
            user_similarities = user_similarity_df.loc[user_id].sort_values(ascending=False)
            
            # Get top similar users (excluding self)
            similar_users = user_similarities[1:11].index.tolist()  # Top 10 similar users
            
            if not similar_users:
                return {}
            
            # Get games rated by similar users
            similar_user_ratings = user_game_matrix.loc[similar_users]
            
            # Calculate collaborative scores for candidate games
            collaborative_scores = {}
            candidate_urls = {game['URL'] for game in candidates}
            
            for game_url in candidate_urls:
                if game_url in similar_user_ratings.columns:
                    # Get ratings for this game from similar users
                    game_ratings = similar_user_ratings[game_url]
                    valid_ratings = game_ratings[game_ratings > 0]  # Only positive ratings
                    
                    if len(valid_ratings) > 0:
                        # Calculate weighted score based on user similarities
                        total_weight = 0
                        weighted_sum = 0
                        
                        for similar_user in valid_ratings.index:
                            similarity = user_similarities[similar_user]
                            rating = valid_ratings[similar_user]
                            weighted_sum += similarity * rating
                            total_weight += similarity
                        
                        if total_weight > 0:
                            collaborative_scores[game_url] = weighted_sum / total_weight
            
            return collaborative_scores
            
        except Exception as e:
            print(f"Error getting collaborative scores for candidates: {e}")
            return {}

    def _combine_content_collaborative_scores(self, content_candidates, collaborative_scores, top_n):
        """Combine content and collaborative scores to rank candidates"""
        try:
            combined_scores = []
            
            for game in content_candidates:
                game_url = game['URL']
                content_score = game.get('content_score', 0)
                collaborative_score = collaborative_scores.get(game_url, 0)
                
                # Calculate combined score (weighted combination)
                # If no collaborative score, use content score only
                if collaborative_score > 0:
                    # Combine scores: 40% content + 60% collaborative
                    combined_score = (content_score * 0.4) + (collaborative_score * 0.6)
                else:
                    # Fallback to content score only
                    combined_score = content_score * 0.8  # Slightly penalize for no collaborative data
                
                game_data = game.copy()
                game_data['combined_score'] = combined_score
                game_data['content_score'] = content_score
                game_data['collaborative_score'] = collaborative_score
                combined_scores.append(game_data)
            
            # Sort by combined score and return top N
            combined_scores.sort(key=lambda x: x['combined_score'], reverse=True)
            
            return combined_scores[:top_n]
            
        except Exception as e:
            print(f"Error combining scores: {e}")
            return content_candidates[:top_n]