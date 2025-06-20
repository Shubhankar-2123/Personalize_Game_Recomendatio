from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from recommender import GameRecommender
import os
from datetime import datetime
from database import db_manager
import math

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this in production

# Initialize recommender
try:
    recommender = GameRecommender()
    print("✅ GameRecommender initialized successfully")
except Exception as e:
    print(f"⚠️  Warning: GameRecommender initialization failed: {e}")
    recommender = None

@app.route('/')
def index():
    """Home page with popular games and genres"""
    try:
        page = int(request.args.get('page', 1))
        per_page = 12
        
        if recommender:
            popular_games = recommender.get_popular_games(per_page)
        else:
            popular_games = []
        
        # Get all genres for the sidebar
        genres = db_manager.get_all_genres()
        
        return render_template('index.html', 
                             games=popular_games,
                             genres=genres,
                             current_page=page,
                             total_pages=1)  # Only one page for popular games
    except Exception as e:
        print(f"Error loading index page: {e}")
        return render_template('index.html', games=[], genres=[], current_page=1, total_pages=1)

@app.route('/search')
def search():
    """Search games"""
    try:
        query = request.args.get('q', '')
        page = int(request.args.get('page', 1))
        per_page = 12
        
        if not query:
            return redirect(url_for('index'))
        
        games, total = db_manager.search_games(query, page, per_page)
        total_pages = math.ceil(total / per_page)
        genres = db_manager.get_all_genres()
        
        return render_template('search.html',
                             games=games,
                             query=query,
                             genres=genres,
                             current_page=page,
                             total_pages=total_pages)
    except Exception as e:
        print(f"Error searching games: {e}")
        return render_template('search.html', 
                             games=[],
                             query=query,
                             genres=[],
                             current_page=1,
                             total_pages=1)

@app.route('/genre/<genre>')
def genre(genre):
    """Browse games by genre"""
    try:
        page = int(request.args.get('page', 1))
        per_page = 12
        
        games, total = db_manager.get_games_by_genre(genre, page, per_page)
        total_pages = math.ceil(total / per_page)
        genres = db_manager.get_all_genres()
        
        return render_template('genre.html',
                             games=games,
                             current_genre=genre,
                             genres=genres,
                             current_page=page,
                             total_pages=total_pages)
    except Exception as e:
        print(f"Error loading genre page: {e}")
        return render_template('genre.html',
                             games=[],
                             current_genre=genre,
                             genres=[],
                             current_page=1,
                             total_pages=1)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if not username or not password:
            flash('Please fill in all fields', 'error')
            return render_template('register.html')
        
        try:
            # Check if MongoDB is connected
            if not db_manager.is_connected():
                flash('User registration is currently unavailable. Please try again later.', 'error')
                return render_template('register.html')
            
            # Check if user already exists
            existing_user = db_manager.get_user_by_username(username)
            if existing_user:
                flash('Username already exists', 'error')
                return render_template('register.html')
            
            # Create new user
            password_hash = generate_password_hash(password)
            user_id = db_manager.create_user(username, password_hash)
            
            if user_id:
                flash('Registration successful! Please log in.', 'success')
                return redirect(url_for('login'))
            else:
                flash('Registration failed. Please try again later.', 'error')
                
        except Exception as e:
            print(f"Registration error: {e}")
            flash('Registration failed. Please try again later.', 'error')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if not username or not password:
            flash('Please fill in all fields', 'error')
            return render_template('login.html')
        
        try:
            # Check if MongoDB is connected
            if not db_manager.is_connected():
                flash('Database not available. Please try again later.', 'error')
                return render_template('login.html')
            
            # Get user from database
            user = db_manager.get_user_by_username(username)
            
            if user and check_password_hash(user['password'], password):
                session['user_id'] = str(user['_id'])
                session['username'] = user['username']
                flash('Login successful!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Invalid username or password', 'error')
                
        except Exception as e:
            print(f"Login error: {e}")
            flash('Login failed. Please try again.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/game/<game_name>')
def game_detail(game_name):
    """Game detail page"""
    try:
        # Get referrer from query parameter
        referrer = request.args.get('ref', 'index')
        
        if recommender:
            game = recommender.get_game_by_name(game_name)
        else:
            game = None
        
        if not game:
            flash('Game not found', 'error')
            return redirect(url_for('index'))
        
        # Get user's rating for this game
        user_rating = None
        if 'user_id' in session:
            try:
                if db_manager.is_connected():
                    user_ratings = db_manager.get_user_ratings(session['user_id'])
                    for rating in user_ratings:
                        if rating['game_url'] == game['URL']:
                            user_rating = rating['value']
                            break
            except Exception as e:
                print(f"Error getting user rating: {e}")
        
        return render_template('game_detail.html', game=game, user_rating=user_rating, referrer=referrer)
        
    except Exception as e:
        print(f"Error loading game detail: {e}")
        flash('Error loading game details', 'error')
        return redirect(url_for('index'))

@app.route('/rate/<game_name>', methods=['POST'])
def rate_game(game_name):
    """Rate a game"""
    if 'user_id' not in session:
        flash('Please log in to rate games', 'error')
        return redirect(url_for('login'))
    
    try:
        rating = float(request.form['rating'])
        if rating < 1 or rating > 5:
            flash('Rating must be between 1 and 5', 'error')
            return redirect(url_for('game_detail', game_name=game_name))
        
        if recommender:
            game = recommender.get_game_by_name(game_name)
        else:
            game = None
        
        if not game:
            flash('Game not found', 'error')
            return redirect(url_for('index'))
        
        # Check if MongoDB is connected
        if not db_manager.is_connected():
            flash('Database not available. Please try again later.', 'error')
            return redirect(url_for('game_detail', game_name=game_name))
        
        # Record the rating
        success = recommender.record_interaction(
            session['user_id'], 
            game['URL'], 
            'rating', 
            rating
        )
        
        if success:
            flash('Rating saved successfully!', 'success')
        else:
            flash('Failed to save rating. Please try again.', 'error')
            
    except ValueError:
        flash('Invalid rating value', 'error')
    except Exception as e:
        print(f"Error rating game: {e}")
        flash('Error saving rating. Please try again.', 'error')
    
    return redirect(url_for('game_detail', game_name=game_name))

@app.route('/profile')
def profile():
    """User profile page"""
    if 'user_id' not in session:
        flash('Please log in to view your profile', 'error')
        return redirect(url_for('login'))
    
    try:
        # Check if MongoDB is connected
        if not db_manager.is_connected():
            flash('Database not available. Please try again later.', 'error')
            return render_template('profile.html', user_ratings=[], username=session.get('username', ''))
        
        # Get user's ratings
        user_ratings = db_manager.get_user_ratings(session['user_id'])
        
        # Get game details for each rating
        rated_games = []
        for rating in user_ratings:
            if recommender:
                game = recommender.get_game_details(rating['game_url'])
                if game:
                    rated_games.append({
                        **game,
                        'user_rating': rating['value'],
                        'rating_timestamp': str(rating['timestamp'])
                    })
        
        return render_template('profile.html', user_ratings=rated_games, username=session.get('username', ''))
        
    except Exception as e:
        print(f"Error loading profile: {e}")
        flash('Error loading profile', 'error')
        return render_template('profile.html', user_ratings=[], username=session.get('username', ''))

@app.route('/recommendations')
def recommendations():
    """Personalized recommendations"""
    if 'user_id' not in session:
        flash('Please log in to view recommendations', 'error')
        return redirect(url_for('login'))
    
    try:
        if recommender:
            recommended_games = recommender.get_recommendations(session['user_id'], 12)
        else:
            recommended_games = []
        
        return render_template('recomendations.html', games=recommended_games)
        
    except Exception as e:
        print(f"Error loading recommendations: {e}")
        flash('Error loading recommendations', 'error')
        return render_template('recomendations.html', games=[])

@app.route('/setup/load-data')
def setup_load_data():
    """Load initial games data into database (MongoDB or SQLite)"""
    try:
        csv_path = 'data/Game_processed_data.csv'
        if not os.path.exists(csv_path):
            return jsonify({'error': 'Games CSV file not found'}), 404
        
        try:
            db_manager.load_games_from_csv(csv_path)
            return jsonify({'message': 'Games data loaded successfully!'})
        except Exception as e:
            print(f"Error loading games data: {e}")
            return jsonify({'error': 'Failed to load games data'}), 500
            
    except Exception as e:
        print(f"Error in setup: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        mongodb_status = "connected" if db_manager.is_connected() else "disconnected"
        recommender_status = "ready" if recommender and recommender.games_df is not None else "not_ready"
        
        return jsonify({
            'status': 'ok',
            'mongodb': mongodb_status,
            'recommender': recommender_status,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

if __name__ == '__main__':
    print("🚀 Starting Game Recommendation System...")
    print("📊 MongoDB Status:", "Connected" if db_manager.is_connected() else "Not Connected")
    print("🎮 Recommender Status:", "Ready" if recommender and recommender.games_df is not None else "Not Ready")
    
    if not db_manager.is_connected():
        print("\n⚠️  MongoDB is not connected!")
        print("To set up MongoDB Atlas:")
        print("1. Run: python setup_mongodb.py")
        print("2. Follow the setup instructions")
        print("3. Restart the application")
    
    app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)