"""
Oncology Sesh API - app setup (same layout as the Poway Recovery Center API and Open Coding Society flask __init__.py)

Creates the Flask app, CORS, and database objects that model/ and api/ import.
"""
import os

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy


# Load environment variables from .env, no matter which folder main.py is run from
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

# Setup of key Flask object (app); instance folder holds the database
app = Flask(__name__, instance_path=os.path.join(basedir, 'instance'))

# Configure Flask Port, default to : the address the portfolio frontend calls (assets/js/api/config.js)
app.config['FLASK_PORT'] = int(os.environ.get('FLASK_PORT') or 8587)

# Allowed servers for cross-origin resource sharing (CORS)
allowed_origins = [
    'http://localhost:4500',           # portfolio frontend: `make` in the repo root
    'http://127.0.0.1:4500',
    'http://localhost:4000',
    'http://127.0.0.1:4000',
    'https://csp-oncology.github.io',  # Deployed frontend (GitHub Pages: csp-oncology.github.io/portfolio)
    'https://oncologysesh.opencodingsociety.com',  # Deployed frontend (custom domain)
]
# Any other deployed frontend(s), comma separated in .env
allowed_origins += [o.strip() for o in (os.environ.get('ALLOWED_ORIGINS') or '').split(',') if o.strip()]

cors = CORS(
    app,
    supports_credentials=True,
    origins=allowed_origins,
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
)

# Admin defaults
app.config['ADMIN_USER'] = os.environ.get('ADMIN_USER') or 'Sesh Admin'
app.config['ADMIN_UID'] = os.environ.get('ADMIN_UID') or 'admin'
app.config['ADMIN_EMAIL'] = os.environ.get('ADMIN_EMAIL') or None
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD') or os.environ.get('DEFAULT_PASSWORD') or 'password'
# Password given to every other seeded user until they change it on their profile page
app.config['DEFAULT_PASSWORD'] = os.environ.get('DEFAULT_PASSWORD') or 'password'
# Members created on first run: (name, uid, role, password). Existing accounts keep their password
# but get the role listed here. Add the team here, e.g. ('Anika Seksaria', 'anikaseksaria', 'Admin', None);
# a password of None reads <FIRSTNAME>_PASSWORD from .env (e.g. ANIKA_PASSWORD), falling back to DEFAULT_PASSWORD.
def _ocs_member(prefix, name, uid, name_key=None):
    """ An Open Coding Society account from the .env keys OCS flask uses (e.g. TEACHER_USER, TEACHER_UID, TEACHER_PASSWORD) """
    return (os.environ.get(name_key or f'{prefix}_USER') or name,
            os.environ.get(f'{prefix}_UID') or uid,
            'Admin',
            os.environ.get(f'{prefix}_PASSWORD'))

app.config['MEMBERS'] = [
    # The Open Coding Society accounts, all admins here so they can read survey responses and messages
    ('Thomas Edison', 'toby', 'Admin', None),   # THOMAS_PASSWORD, or ADMIN_PASSWORD when ADMIN_UID is toby
    _ocs_member('TEACHER', 'Nikola Tesla', 'niko'),                   # TEACHER_PASSWORD
    _ocs_member('USER', 'Grace Hopper', 'hop', name_key='USER_NAME'),  # USER_PASSWORD
    _ocs_member('MY', 'John Mortensen', 'jm1021', name_key='MY_NAME'), # MY_PASSWORD or DEFAULT_PASSWORD
]

# Browser settings
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'sesh-flask-secret-key-set-SECRET_KEY-in-env'
# Sesh-specific name: OCS's flask uses 'jwt_python_flask' and Poway uses 'prc_jwt'; a distinct name keeps
# a browser holding one of those cookies from sending the wrong one
app.config['JWT_TOKEN_NAME'] = os.environ.get('JWT_TOKEN_NAME') or 'sesh_jwt'
app.config['JWT_TOKEN_MAX_AGE'] = int(os.environ.get('JWT_TOKEN_MAX_AGE') or 604800)  # 1 week
# Production = frontend on GitHub Pages + backend on its own HTTPS domain,
# which needs SameSite=None; Secure cookies (same switch OCS uses)
app.config['IS_PRODUCTION'] = (os.environ.get('IS_PRODUCTION') or 'false').lower() == 'true'
# Admin login page session cookie: HTTPS-only when deployed
app.config['SESSION_COOKIE_SECURE'] = app.config['IS_PRODUCTION']
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_NAME'] = 'sesh_session'  # Avoid colliding with other apps' "session" cookie

# News: synced from Sesh's own News page (model/news.py), re-checked at most this often
app.config['NEWS_SITE_URL'] = (os.environ.get('NEWS_SITE_URL') or 'https://www.oncologysesh.com').rstrip('/')
app.config['NEWS_SOURCE_URL'] = app.config['NEWS_SITE_URL'] + '/news'
app.config['NEWS_REFRESH_SECONDS'] = int(os.environ.get('NEWS_REFRESH_SECONDS') or 3600)  # 1 hour

# Database settings - SQLite in instance/volumes/ (OCS layout)
dbName = 'user_management'
os.makedirs(os.path.join(app.instance_path, 'volumes'), exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or \
    'sqlite:///' + os.path.join(app.instance_path, 'volumes', dbName + '.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
