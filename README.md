# Game Recommendation System

A personalized game recommendation system built with Flask, MongoDB, and machine learning algorithms. This application provides intelligent game recommendations based on user preferences and collaborative filtering.

## 🎮 Features

- **Personalized Recommendations**: Get game suggestions based on your ratings and preferences
- **Popular Games**: Browse trending and highly-rated games
- **Search & Filter**: Search games by name, developer, or genre
- **User Authentication**: Register and login to save your preferences
- **Rating System**: Rate games to improve your recommendations
- **Genre Browsing**: Explore games by genre categories
- **Responsive Design**: Modern, mobile-friendly interface

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- MongoDB Atlas account (optional, for user features)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Personalize_Game_Recomendatio
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables** (optional)
   
   Create a `.env` file in the root directory:
   ```env
   MONGODB_URI=mongodb+srv://your_username:your_password@your_cluster.mongodb.net/your_database?retryWrites=true&w=majority
   MONGODB_DB_NAME=game_recommender
   MONGODB_USERS_COLLECTION=users
   MONGODB_INTERACTIONS_COLLECTION=interactions
   SECRET_KEY=your-secret-key-here
   ```

4. **Load game data**
   ```bash
   python app.py
   ```
   Then visit `http://localhost:3000/setup/load-data` to load the games data.

5. **Run the application**
   ```bash
   python app.py
   ```
   
   The application will be available at `http://localhost:3000`

## 🏗️ Architecture

### Backend
- **Flask**: Web framework
- **MongoDB**: User data and interactions storage
- **SQLite**: Game data storage
- **Scikit-learn**: Machine learning algorithms
- **Pandas**: Data processing

### Frontend
- **Bootstrap 5**: Responsive UI framework
- **Custom CSS**: Gaming-themed styling
- **Jinja2**: Template engine

### Machine Learning
- **Content-Filtered Collaborative Filtering**: Uses content-based filtering to generate candidates, then ranks them with collaborative filtering
- **Content-based Filtering**: Game similarity based on features
- **Collaborative Filtering**: User similarity based on ratings
- **TF-IDF Vectorization**: Text feature extraction

## 📊 Data Structure

### Games Data
- Game metadata (name, description, developer)
- Ratings and review counts
- Genre classifications
- App store URLs and icons

### User Data
- User authentication
- Game ratings and interactions
- Recommendation history

## 🔧 Configuration

The application uses a hybrid database approach:
- **SQLite**: Stores game data (fast, reliable)
- **MongoDB**: Stores user data and interactions (scalable)

If MongoDB is not configured, the application will run with limited user features.

## 🧪 Testing

Run the test suite to verify everything is working:

```bash
python test_setup.py
```

## 📁 Project Structure

```
Personalize_Game_Recomendatio/
├── app.py                 # Main Flask application
├── config.py              # Configuration settings
├── database.py            # Database management
├── recommender.py         # ML recommendation engine
├── requirements.txt       # Python dependencies
├── test_setup.py         # System test script
├── data/                  # Data files
│   ├── Game_processed_data.csv
│   ├── recommendations.db
│   └── user_interactions.csv
├── static/               # Static assets
│   └── style.css
└── templates/            # HTML templates
    ├── base.html
    ├── index.html
    ├── game_detail.html
    ├── recommendations.html
    └── ...
```

## 🚀 Deployment

### Local Development
```bash
python app.py
```

### Production (with Gunicorn)
```bash
gunicorn app:app
```

### Environment Variables
- `MONGODB_URI`: MongoDB connection string
- `SECRET_KEY`: Flask secret key
- `DEBUG`: Enable debug mode (optional)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License.

## 🆘 Support

If you encounter any issues:
1. Check the test results: `python test_setup.py`
2. Verify your environment variables
3. Ensure all dependencies are installed
4. Check the application logs for error messages

## 🎯 Roadmap

- [ ] Advanced recommendation algorithms
- [ ] Social features (friends, sharing)
- [ ] Game reviews and comments
- [ ] Mobile app version
- [ ] API endpoints for external integrations