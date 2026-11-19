""" Preferences API in the shape the Open Coding Society dashboard expects from its Spring backend,
so the portfolio's copy of assets/js/pages/dashboard/preferences.js works unchanged:

  GET    /api/person/get                  the logged-in user (login check)
  GET    /api/user/preferences            saved preferences in backend format, {} if none
  POST   /api/user/preferences            save preferences (PUT does the same)
  DELETE /api/user/preferences            reset to the site defaults

Preferences are stored on the user in the frontend format (model/user.py clean_preferences).
"""
import json

from flask import Blueprint, g, jsonify, request

from api.jwt_authorize import token_required
from model.user import clean_preferences


preferences_api = Blueprint('preferences_api', __name__, url_prefix='/api')

# Frontend key -> Spring (backend) key, as in preferences.js FormatConverter
BACKEND_KEYS = {
    'bg': 'backgroundColor', 'text': 'textColor', 'font': 'fontFamily', 'size': 'fontSize',
    'accent': 'accentColor', 'selectionColor': 'selectionColor', 'buttonStyle': 'buttonStyle',
    'language': 'language', 'ttsVoice': 'ttsVoice', 'ttsRate': 'ttsRate', 'ttsPitch': 'ttsPitch',
    'ttsVolume': 'ttsVolume',
}


def to_backend(user):
    """ The user's preferences in backend format; {} when no theme is saved (the frontend's 'none') """
    prefs = user.preferences
    if not (prefs.get('bg') or prefs.get('text')):
        return {}
    data = {backend: prefs[key] for key, backend in BACKEND_KEYS.items() if key in prefs}
    data['customThemes'] = json.dumps(prefs.get('customThemes', {}))
    data['id'] = user.id
    return data


def from_backend(body):
    """ A backend-format request body as frontend-format preferences """
    prefs = {key: body[backend] for key, backend in BACKEND_KEYS.items() if backend in body}
    themes = body.get('customThemes')
    if isinstance(themes, str):
        try:
            themes = json.loads(themes or '{}')
        except ValueError:
            themes = {}
    if isinstance(themes, dict):
        prefs['customThemes'] = themes
    return prefs


@preferences_api.get('/person/get')
@token_required()
def person_get():
    return jsonify(g.current_user.read())


@preferences_api.get('/user/preferences')
@token_required()
def get_preferences():
    return jsonify(to_backend(g.current_user))


@preferences_api.route('/user/preferences', methods=['POST', 'PUT'])
@token_required()
def save_preferences():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return {"message": "Preferences must be an object"}, 400
    user = g.current_user
    prefs = clean_preferences(from_backend(body))
    user.update({'preferences': prefs})
    return jsonify(to_backend(user))


@preferences_api.delete('/user/preferences')
@token_required()
def delete_preferences():
    g.current_user.update({'preferences': {}})
    return {"message": "Preferences reset"}
