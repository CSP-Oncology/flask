""" User model and default users (same role as Open Coding Society flask model/user.py) """
import json
import os
import re
from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from __init__ import app, db


EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
PHONE_PATTERN = re.compile(r'^\+?[\d\s().-]{7,20}$')
UID_PATTERN = re.compile(r'^[A-Za-z0-9._-]{3,40}$')

# Site preferences a user can save to their account, in the same shape as the Open Coding
# Society dashboard (assets/js/pages/dashboard/preferences.js on the portfolio): colors, font,
# size, button style, language, text-to-speech, and saved custom themes.
HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')
# Font stacks only: letters, digits, spaces, commas, quotes and hyphens (they end up in CSS)
FONT_STACK = re.compile(r"^[A-Za-z0-9 ,'\"-]{1,160}$")
LANGUAGES = {'', 'en', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'zh-CN', 'zh-TW', 'ja', 'ko',
             'ar', 'hi', 'vi', 'th', 'nl', 'pl', 'tr', 'uk', 'he', 'fa'}
BUTTON_STYLES = {'default', 'rounded', 'rounded-all', 'square', 'pill'}
MAX_CUSTOM_THEMES = 10


def _number(value, low, high):
    """ value as a float within [low, high], or None """
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def clean_theme(value):
    """ The look part of a preferences object (colors, font, size, button style, emoji) """
    if not isinstance(value, dict):
        return {}
    theme = {}
    for key in ('bg', 'text', 'accent', 'selectionColor'):
        if isinstance(value.get(key), str) and HEX_COLOR.match(value[key]):
            theme[key] = value[key]
    if isinstance(value.get('font'), str) and FONT_STACK.match(value['font']):
        theme['font'] = value['font']
    size = _number(value.get('size'), 10, 32)
    if size is not None:
        theme['size'] = int(size)
    if value.get('buttonStyle') in BUTTON_STYLES:
        theme['buttonStyle'] = value['buttonStyle']
    decor = value.get('decor')
    if isinstance(decor, list):
        theme['decor'] = [d for d in decor if isinstance(d, str) and 0 < len(d) <= 8][:6]
    if value.get('source') == 'ai':
        theme['source'] = 'ai'
    return theme


def clean_preferences(value):
    """ Keep only known preferences with valid values; returns None if value isn't a dict """
    if not isinstance(value, dict):
        return None
    prefs = clean_theme(value)
    prefs.pop('source', None)
    if value.get('language') in LANGUAGES:
        prefs['language'] = value['language']
    if isinstance(value.get('ttsVoice'), str) and len(value['ttsVoice']) <= 200:
        prefs['ttsVoice'] = value['ttsVoice']
    for key, low, high in (('ttsRate', 0.5, 2), ('ttsPitch', 0.5, 2), ('ttsVolume', 0, 1)):
        number = _number(value.get(key), low, high)
        if number is not None:
            prefs[key] = number
    themes = value.get('customThemes')
    if isinstance(themes, dict):
        prefs['customThemes'] = {
            name.strip()[:30]: clean_theme(theme)
            for name, theme in list(themes.items())[:MAX_CUSTOM_THEMES]
            if isinstance(name, str) and name.strip()
        }
    return prefs


class User(db.Model):
    """
    User Model

    Attributes:
        id (Column): Primary key.
        _name (Column): The user's full name.
        _uid (Column): Unique username, used to log in.
        _email (Column): Optional unique email address, can also be used to log in.
        _phone (Column): Optional phone number.
        _password (Column): Hashed password.
        _role (Column): "User" or "Admin".
        token_version (Column): Bumped on password change so older login tokens stop working.
        created_at (Column): When the account was created.
        _preferences (Column): Saved site preferences (see clean_preferences) as JSON.
    """
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    _name = db.Column(db.String(255), unique=False, nullable=False)
    _uid = db.Column(db.String(255), unique=True, nullable=False)
    _email = db.Column(db.String(255), unique=True, nullable=True)
    _phone = db.Column(db.String(32), unique=False, nullable=True)
    _password = db.Column(db.String(255), unique=False, nullable=False)
    _role = db.Column(db.String(20), default="User", nullable=False)
    token_version = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    _preferences = db.Column(db.Text, nullable=True)

    def __init__(self, name, uid, password=None, email=None, phone=None, role="User"):
        self._name = name
        self._uid = uid.strip().lower()
        self._email = email.strip().lower() if email else None
        self._phone = phone.strip() if phone else None
        self._role = role
        self.token_version = 0
        self.set_password(password or app.config['DEFAULT_PASSWORD'])

    @property
    def name(self):
        return self._name

    @property
    def uid(self):
        return self._uid

    @property
    def email(self):
        return self._email

    @property
    def phone(self):
        return self._phone

    @property
    def role(self):
        return self._role

    def is_admin(self):
        return self._role == "Admin"

    def set_password(self, password):
        """ Hash the password and invalidate any login tokens issued before the change """
        self._password = generate_password_hash(password, "pbkdf2:sha256", salt_length=10)
        self.token_version = (self.token_version or 0) + 1

    def is_password(self, password):
        return check_password_hash(self._password, password)

    @staticmethod
    def validate(name=None, uid=None, email=None, phone=None, password=None):
        """ Returns an error message for the first invalid field supplied, or None """
        if name is not None and not name.strip():
            return 'Name is required'
        if uid is not None and not UID_PATTERN.match(uid.strip()):
            return 'Username must be 3-40 letters, numbers, dots, dashes or underscores'
        if email and not EMAIL_PATTERN.match(email.strip()):
            return 'Please enter a valid email address'
        if phone and not PHONE_PATTERN.match(phone.strip()):
            return 'Please enter a valid phone number'
        if password is not None and len(password) < 6:
            return 'Password must be at least 6 characters'
        return None

    def create(self):
        """ Add the user to the database; returns None if the username or email is taken """
        try:
            db.session.add(self)
            db.session.commit()
            return self
        except IntegrityError:
            db.session.rollback()
            return None

    def read(self):
        return {
            "id": self.id,
            "name": self.name,
            "uid": self.uid,
            "email": self.email or "",
            "phone": self.phone or "",
            "role": self.role,
            "is_admin": self.is_admin(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "preferences": self.preferences,
        }

    @property
    def preferences(self):
        try:
            return clean_preferences(json.loads(self._preferences or '{}')) or {}
        except ValueError:
            return {}

    def update(self, inputs):
        """ Update name, email and/or phone from a dict; returns None if the email is taken """
        if 'name' in inputs:
            self._name = inputs['name'].strip()
        if 'email' in inputs:
            self._email = inputs['email'].strip().lower() or None
        if 'phone' in inputs:
            self._phone = inputs['phone'].strip() or None
        if 'preferences' in inputs:
            self._preferences = json.dumps(clean_preferences(inputs['preferences']) or {})
        try:
            db.session.commit()
            return self
        except IntegrityError:
            db.session.rollback()
            return None

    def delete(self):
        db.session.delete(self)
        db.session.commit()


def initUsers():
    """
    Create the database tables and the default users.
    New users are created with their starting password; existing users keep their
    password and profile, but get the role listed here.
    """
    with app.app_context():
        db.create_all()
        # Databases made before the Settings page lack the preferences column; add it
        columns = [c['name'] for c in inspect(db.engine).get_columns('users')]
        if '_preferences' not in columns:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE users ADD COLUMN _preferences TEXT'))
        seeds = [(app.config['ADMIN_USER'], app.config['ADMIN_UID'], 'Admin',
                  app.config['ADMIN_PASSWORD'], app.config['ADMIN_EMAIL'])]
        for name, uid, role in app.config['MEMBERS']:
            password = os.environ.get(name.split()[0].upper() + '_PASSWORD') or app.config['DEFAULT_PASSWORD']
            seeds.append((name, uid, role, password, None))

        for name, uid, role, password, email in seeds:
            user = User.query.filter_by(_uid=uid).first()
            if user is None:
                User(name=name, uid=uid, email=email, password=password, role=role).create()
            elif user.role != role:
                user._role = role
                db.session.commit()
