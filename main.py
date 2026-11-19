"""
Oncology Sesh API - entry point (same layout as the Poway Recovery Center API and Open Coding Society flask main.py)

Run it with:
    python main.py

On start it creates the user management database (instance/volumes/user_management.db),
adds the default users, and serves the API on http://localhost:8587
"""
from flask import render_template

from __init__ import app, db
from api.admin import admin
from api.contact import contact_api
from api.user import user_api
from api.preferences import preferences_api
from api.news import news_api
from model.contact import initContacts
from model.news import initNews
from model.user import initUsers


# Register URIs for API endpoints
app.register_blueprint(admin)
app.register_blueprint(user_api)
app.register_blueprint(preferences_api)
app.register_blueprint(contact_api)
app.register_blueprint(news_api)


@app.route('/')
def index():
    # Same home page as Open Coding Society flask, with Login in the navbar for admin access
    return render_template('index.html')


# Create the database, default users, contact messages table and Sesh's current news whenever the app starts (python main.py or gunicorn)
initUsers()
initContacts()
initNews()

if __name__ == "__main__":
    print(f"Database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print(f"Server running: http://localhost:{app.config['FLASK_PORT']}")
    app.run(debug=True, host="0.0.0.0", port=app.config['FLASK_PORT'], use_reloader=False)
