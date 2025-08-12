from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from recommender import GameRecommender
import os
from datetime import datetime, timezone
from database import db_manager
import math
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from markupsafe import escape
import logging
from logging.handlers import RotatingFileHandler
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from bson import ObjectId
from config import Config
from functools import wraps

app = Flask(__name__)
# Use a fixed secret key for CSRF to work reliably across requests
app.secret_key = 'your-very-secret-key'  # Use a strong, random value in production!

# Add max function to Jinja2 environment for pagination
app.jinja_env.globals.update(max=max, min=min)

# Initialize rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
limiter.init_app(app)

# Initialize recommender
try:
    recommender = GameRecommender()
    print("✅ GameRecommender initialized successfully")
except Exception as e:
    print(f"⚠️  Warning: GameRecommender initialization failed: {e}")
    recommender = None

if not app.debug:
    file_handler = RotatingFileHandler('logs/game_recommender.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Game Recommender startup')

app.config.update(
    MAIL_SERVER=Config.MAIL_SERVER,
    MAIL_PORT=Config.MAIL_PORT,
    MAIL_USE_TLS=Config.MAIL_USE_TLS,
    MAIL_USERNAME=Config.MAIL_USERNAME,
    MAIL_PASSWORD=Config.MAIL_PASSWORD,
    MAIL_DEFAULT_SENDER=Config.MAIL_DEFAULT_SENDER
)
mail = Mail(app)
serializer = URLSafeTimedSerializer(app.secret_key)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin', False):
            flash('Admin access required.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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
        query = escape(request.args.get('q', ''))
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
        
        genre = escape(genre)
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
    """User registration with validation"""
    if request.method == 'POST':
        username = escape(request.form.get('username', '').strip())
        password = request.form.get('password', '').strip()
        
        # Input validation
        if not username or not password:
            flash('Username and password are required', 'error')
            return render_template('register.html')
        
        if len(username) < 4 or len(username) > 20:
            flash('Username must be between 4 and 20 characters', 'error')
            return render_template('register.html')
            
        if len(password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return render_template('register.html')
            
        if not any(char.isdigit() for char in password):
            flash('Password must contain at least one number', 'error')
            return render_template('register.html')
            
        if not any(char.isupper() for char in password):
            flash('Password must contain at least one uppercase letter', 'error')
            return render_template('register.html')
        
        try:
            # Check if MongoDB is connected
            if not db_manager.is_connected():
                flash('User registration is currently unavailable. Please try again later.', 'error')
                return render_template('register.html')
            
            # Check if user already exists
            existing_user = db_manager.get_user_by_username(username)
            if existing_user:
                flash('Username already exists. Please choose a different username.', 'error')
                return render_template('register.html')
            
            # Create new user
            password_hash = generate_password_hash(password)
            email = request.form.get('email', '').strip() # Get email from form
            user_id = db_manager.create_user(username, password_hash, email)
            
            if user_id:
                # Send verification email
                token = serializer.dumps(str(user_id), salt='email-verify')
                verify_url = url_for('verify_email', token=token, _external=True)
                msg = Message('Verify Your Email', recipients=[email], sender=app.config['MAIL_DEFAULT_SENDER'])
                msg.body = f'Click the link to verify your account: {verify_url}\nIf you did not register, ignore this email.'
                mail.send(msg)
                flash('Registration successful! Please check your email to verify your account.', 'success')
                return redirect(url_for('login'))
            else:
                flash('Registration failed due to a server error. Please try again later.', 'error')
                
        except Exception as e:
            print(f"Registration error: {e}")
            flash('Registration failed due to a technical issue. Our team has been notified.', 'error')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        username = escape(request.form['username'])
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
                if user and not user.get('verified', False):
                    flash('Please verify your email before logging in.', 'error')
                    return render_template('login.html')
                session['user_id'] = str(user['_id'])
                session['username'] = user['username']
                session['is_admin'] = user.get('is_admin', False)
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
    session.pop('is_admin', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/game/<int:game_id>')
def game_detail(game_id):
    """Game detail page"""
    try:
        referrer = request.args.get('ref', 'index')
        if recommender:
            game = recommender.get_game_by_id(game_id)
        else:
            game = None
        if not game:
            flash('Game not found', 'error')
            return redirect(url_for('index'))
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

@app.route('/rate/<int:game_id>', methods=['POST'])
def rate_game(game_id):
    print(request.form)  # Debug: Print all form data to the console
    if 'user_id' not in session:
        flash('Please log in to rate games', 'error')
        return redirect(url_for('login'))
    try:
        rating = float(escape(request.form['rating']))
        if rating < 1 or rating > 5:
            flash('Rating must be between 1 and 5', 'error')
            return redirect(url_for('game_detail', game_id=game_id))
        if recommender:
            game = recommender.get_game_by_id(game_id)
        else:
            game = None
        if not game:
            flash('Game not found', 'error')
            return redirect(url_for('index'))
        if not db_manager.is_connected():
            flash('Database not available. Please try again later.', 'error')
            return redirect(url_for('game_detail', game_id=game_id))
        if recommender:
            success = recommender.record_interaction(
                session['user_id'],
                game['URL'],
                'rating',
                rating
            )
        else:
            success = False
        if success:
            flash('Rating saved successfully!', 'success')
        else:
            flash('Failed to save rating. Please try again.', 'error')
    except ValueError:
        flash('Invalid rating value', 'error')
    except Exception as e:
        print(f"Error rating game: {e}")
        flash('Error saving rating. Please try again.', 'error')
    return redirect(url_for('game_detail', game_id=game_id))

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

        # Sort ratings by timestamp (most recent first)
        user_ratings_sorted = sorted(
            user_ratings, 
            key=lambda r: r['timestamp'], 
            reverse=True
        )

        # Get only the 10 most recent ratings
        user_ratings_sorted = user_ratings_sorted[:10]

        # Get game details for each rating
        rated_games = []
        for rating in user_ratings_sorted:  # <-- use the sorted and sliced list
            if recommender:
                game = recommender.get_game_details(rating['game_url'])
                if game:
                    rated_games.append({
                        **game,
                        'user_rating': rating['value'],
                        'rating_timestamp': str(rating['timestamp'])
                    })
        
        return render_template('profile.html', rated_games=rated_games, username=session.get('username', ''))        
    except Exception as e:
        print(f"Error loading profile: {e}")
        flash('Error loading profile', 'error')
        return render_template('profile.html', rated_games=[], username=session.get('username', ''))
@app.route('/profile/edit', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db_manager.get_user_by_username(session['username'])
    if request.method == 'POST':
        new_username = escape(request.form.get('username', '').strip())
        new_email = escape(request.form.get('email', '').strip())
        # Validation
        if not new_username or len(new_username) < 4 or len(new_username) > 20:
            flash('Username must be between 4 and 20 characters.', 'error')
            return render_template('edit_profile.html', user=user)
        if new_email and ('@' not in new_email or '.' not in new_email):
            flash('Please enter a valid email address.', 'error')
            return render_template('edit_profile.html', user=user)
        # Update in database
        success = db_manager.update_user_profile(user['_id'], new_username, new_email)
        if success:
            session['username'] = new_username
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('profile'))
        else:
            flash('Failed to update profile. Please try again.', 'error')
    return render_template('edit_profile.html', user=user)

@app.route('/recommendations')
def recommendations():
    """Interest-based recommendations based on user preferences"""
    if 'user_id' not in session:
        flash('Please log in to view recommendations', 'error')
        return redirect(url_for('login'))
    
    try:
        # Check if user has rated any games
        user_ratings = db_manager.get_user_ratings(session['user_id'])
        
        if not user_ratings:
            flash('Please rate some games first to get personalized recommendations!', 'info')
            return render_template('recommendations.html', games=[], no_ratings=True)
        
        if recommender:
            # Get user's current ratings for debugging
            user_ratings = db_manager.get_user_ratings(session['user_id'])
            print(f"🎯 User {session['user_id']} has {len(user_ratings)} ratings")
            
            # Use content-filtered collaborative recommendations
            recommended_games = recommender.get_recommendations(session['user_id'], 12)
            
            if recommended_games:
                print(f"✅ Recommendations: {len(recommended_games)} games")
                for i, game in enumerate(recommended_games[:5]):
                    predicted_rating = game.get('predicted_rating', 0)
                    avg_rating = game.get('avg_rating', 0)
                    score = game.get('recommendation_score', 0)
                    print(f"   {i+1}. {game.get('Name', 'N/A')} (Predicted: {predicted_rating:.1f}, Avg: {avg_rating:.1f}, Score: {score:.2f})")
            else:
                flash('Not enough data for personalized recommendations. Please rate more games!', 'info')
                return render_template('recommendations.html', games=[], no_ratings=True)
        else:
            recommended_games = []
            flash('Recommendation system not available', 'error')
            return render_template('recommendations.html', games=[], no_ratings=True)
        
        # Add cache-busting headers to prevent browser caching
        response = make_response(render_template('recommendations.html', games=recommended_games, no_ratings=False))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
        
    except Exception as e:
        print(f"Error loading recommendations: {e}")
        flash('Error loading recommendations. Please try again.', 'error')
        return render_template('recommendations.html', games=[], no_ratings=True)

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
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500

@app.errorhandler(404)
def not_found_error(error):
    app.logger.warning(f"404 error: {error}")
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"500 error: {error}")
    return render_template('500.html'), 500

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = escape(request.form.get('email', '').strip())
        if not email or '@' not in email or '.' not in email:
            flash('Please enter a valid email address.', 'error')
            return render_template('reset_password.html')
        user = db_manager.users_collection.find_one({'email': email})
        if not user:
            flash('No account found with that email.', 'error')
            return render_template('reset_password.html')
        token = serializer.dumps(str(user['_id']), salt='password-reset')
        reset_url = url_for('reset_with_token', token=token, _external=True)
        msg = Message('Password Reset Request', recipients=[email])
        msg.body = f'Click the link to reset your password: {reset_url}\nIf you did not request this, ignore this email.'
        mail.send(msg)
        flash('Password reset email sent! Please check your inbox.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_with_token(token):
    try:
        user_id = serializer.loads(token, salt='password-reset', max_age=3600)
    except SignatureExpired:
        flash('The password reset link has expired.', 'error')
        return redirect(url_for('reset_password'))
    except BadSignature:
        flash('Invalid or tampered password reset link.', 'error')
        return redirect(url_for('reset_password'))
    if request.method == 'POST':
        new_password = request.form.get('password', '').strip()
        if len(new_password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return render_template('reset_with_token.html', token=token)
        db_manager.users_collection.update_one({'_id': ObjectId(user_id)}, {'$set': {'password': generate_password_hash(new_password), 'last_updated': datetime.utcnow()}})
        flash('Your password has been reset. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_with_token.html', token=token)

@app.route('/verify/<token>')
def verify_email(token):
    try:
        user_id = serializer.loads(token, salt='email-verify', max_age=86400)
    except SignatureExpired:
        flash('The verification link has expired.', 'error')
        return redirect(url_for('login'))
    except BadSignature:
        flash('Invalid or tampered verification link.', 'error')
        return redirect(url_for('login'))
    if db_manager.verify_user(user_id):
        flash('Your email has been verified! You can now log in.', 'success')
    else:
        flash('Verification failed. Please contact support.', 'error')
    return redirect(url_for('login'))

@app.route('/admin')
@admin_required
def admin_panel():
    users = db_manager.get_all_users()
    games = db_manager.get_all_games()
    stats = {
        'total_users': len(users),
        'total_games': len(games)
    }
    return render_template('admin.html', stats=stats, users=users, games=games)

@app.route('/docs')
def api_docs():
    return render_template('api_docs.html')

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
    
    app.run(debug=False, host='0.0.0.0', port=3000, use_reloader=False)