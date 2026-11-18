""" Preferences API in the shape the Open Coding Society dashboard expects from its Spring backend,
so the portfolio's copy of assets/js/pages/dashboard/preferences.js and ai-theme.js work unchanged:

  GET    /api/person/get                  the logged-in user (login check)
  GET    /api/user/preferences            saved preferences in backend format, {} if none
  POST   /api/user/preferences            save preferences (PUT does the same)
  DELETE /api/user/preferences            reset to the site defaults
  GET    /api/content/HEAD_CALIBRATION    the user's head-tracking calibration, as a list of rows
  POST   /api/content/HEAD_CALIBRATION    save head-tracking calibration
  POST   /api/user/ai-theme               design a theme from a short description (needs ANTHROPIC_API_KEY)

Preferences are stored on the user in the frontend format (model/user.py clean_preferences).
"""
import json
import os

from flask import Blueprint, g, jsonify, request

from api.jwt_authorize import token_required
from model.user import clean_calibration, clean_preferences, clean_theme


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
    # Calibration is saved separately (HEAD_CALIBRATION), so keep it
    if 'headCalibration' in user.preferences:
        prefs['headCalibration'] = user.preferences['headCalibration']
    user.update({'preferences': prefs})
    return jsonify(to_backend(user))


@preferences_api.delete('/user/preferences')
@token_required()
def delete_preferences():
    user = g.current_user
    kept = {k: v for k, v in user.preferences.items() if k == 'headCalibration'}
    user.update({'preferences': kept})
    return {"message": "Preferences reset"}


@preferences_api.get('/content/HEAD_CALIBRATION')
@token_required()
def get_calibration():
    user = g.current_user
    calibration = user.preferences.get('headCalibration')
    if not calibration:
        return jsonify([])
    # One row, shaped like a Spring content row; userId matches the id /api/person/get returns
    return jsonify([{"id": user.id, "userId": user.id, "body": f"{user.id}-calibration", "metadata": calibration}])


@preferences_api.post('/content/HEAD_CALIBRATION')
@token_required()
def save_calibration():
    body = request.get_json(silent=True) or {}
    calibration = clean_calibration(body.get('metadata'))
    if calibration is None:
        return {"message": "Calibration must be an object"}, 400
    user = g.current_user
    user.update({'preferences': {**user.preferences, 'headCalibration': calibration}})
    return jsonify({"id": user.id, "userId": user.id, "body": f"{user.id}-calibration", "metadata": calibration})


# ---------- AI theme ----------

# The fonts the Settings page offers (pref-font-family options)
AI_FONTS = [
    "'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif",
    "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial",
    "Roboto, system-ui, -apple-system, 'Segoe UI', 'Helvetica Neue', Arial",
    "'Open Sans', Arial, sans-serif",
    "Lato, Arial, sans-serif",
    "Montserrat, Arial, sans-serif",
    "Georgia, 'Times New Roman', Times, serif",
    "'Source Code Pro', monospace",
]

AI_THEME_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Short theme name, at most 30 characters"},
        "description": {"type": "string", "description": "One sentence describing the look"},
        "background": {"type": "string", "description": "Page background as #rrggbb"},
        "text": {"type": "string", "description": "Body text color as #rrggbb"},
        "accent": {"type": "string", "description": "Links and buttons as #rrggbb"},
        "selection": {"type": "string", "description": "Highlighted-text background as #rrggbb"},
        "font": {"type": "string", "enum": AI_FONTS},
        "size": {"type": "integer", "description": "Base text size in px, 13 to 18"},
        "buttonStyle": {"type": "string", "enum": ["default", "rounded-all", "square", "pill"]},
        "decor": {"type": "array", "items": {"type": "string"}, "description": "Three single emoji that fit the theme"},
    },
    "required": ["name", "description", "background", "text", "accent", "selection",
                 "font", "size", "buttonStyle", "decor"],
    "additionalProperties": False,
}

AI_THEME_SYSTEM = (
    "You design color themes for Oncology Sesh, a student website about cancer treatment and "
    "liquid biopsy. Given a short description of a look, return one theme. Text on the background "
    "and the accent on the background must each reach at least 4.5:1 WCAG contrast, and the "
    "background color must be readable as text on an accent-colored button. Keep it tasteful "
    "and easy to read for long passages."
)


def _luminance(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g_, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g_ + 0.0722 * b


def _contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _mix(a, b, share):
    """ a moved `share` of the way toward b """
    return '#' + ''.join(
        f"{round(int(a[i:i + 2], 16) * (1 - share) + int(b[i:i + 2], 16) * share):02x}" for i in (1, 3, 5))


def _readable(color, background):
    """ color, moved toward black or white just far enough to reach 4.5:1 on background """
    target = '#000000' if _luminance(background) > 0.18 else '#ffffff'
    for step in range(0, 21):
        candidate = _mix(color, target, step / 20)
        if _contrast(candidate, background) >= 4.5:
            return candidate
    return target


def generate_theme(prompt):
    """ Ask Claude for a theme; returns (theme, None) or (None, (message, status)) """
    if not os.environ.get('ANTHROPIC_API_KEY'):
        return None, ("AI themes aren't set up on this server yet: add ANTHROPIC_API_KEY to the backend's .env.", 503)
    try:
        import anthropic
    except ImportError:
        return None, ("AI themes need the anthropic package: pip install -r requirements.txt", 503)

    client = anthropic.Anthropic()
    try:
        response = client.beta.messages.create(
            model="claude-opus-5-5",
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": AI_THEME_SCHEMA}},
            system=AI_THEME_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.RateLimitError:
        return None, ("The AI is busy right now. Try again in a minute.", 429)
    except anthropic.APIStatusError as e:
        return None, (f"The AI service answered {e.status_code}.", 502)
    except anthropic.APIConnectionError:
        return None, ("Couldn't reach the AI service.", 502)

    if response.stop_reason == "refusal":
        return None, ("The AI couldn't make that theme. Try describing it another way.", 422)
    text = next((block.text for block in response.content if block.type == "text"), '')
    try:
        data = json.loads(text)
    except ValueError:
        return None, ("The AI's answer couldn't be read. Try again.", 502)

    # Validate like any saved theme, then make sure it's readable whatever the AI picked
    look = clean_theme({
        'bg': data.get('background'), 'text': data.get('text'), 'accent': data.get('accent'),
        'selectionColor': data.get('selection'), 'font': data.get('font'), 'size': data.get('size'),
        'buttonStyle': data.get('buttonStyle'), 'decor': data.get('decor'),
    })
    if not all(k in look for k in ('bg', 'text', 'accent')):
        return None, ("The AI's colors weren't valid. Try again.", 502)
    bg = look['bg']
    text_color = _readable(look['text'], bg)
    accent = _readable(look['accent'], bg)
    return {
        "name": str(data.get('name') or 'AI theme')[:30],
        "description": str(data.get('description') or '')[:200],
        "background": bg,
        "text": text_color,
        "accent": accent,
        "selection": look.get('selectionColor', accent),
        "font": look.get('font', AI_FONTS[0]),
        "size": min(max(look.get('size', 16), 13), 18),
        "buttonStyle": look.get('buttonStyle', 'default'),
        "decor": look.get('decor', [])[:3],
    }, None


@preferences_api.post('/user/ai-theme')
@token_required()
def ai_theme():
    body = request.get_json(silent=True) or {}
    prompt = str(body.get('prompt') or '').strip()
    if not prompt:
        return {"error": "Describe the theme you want first."}, 400
    theme, error = generate_theme(prompt[:200])
    if error:
        return {"error": error[0]}, error[1]
    return jsonify(theme)
