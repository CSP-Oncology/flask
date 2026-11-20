""" Survey response model (same pattern as model/contact.py)

Answers sent from the site's feedback survey (/sesh/survey); admins read them on their
profile page and at Data -> Survey Responses in the backend.
"""
import json
from datetime import datetime, timezone

from __init__ import app, db


class SurveyResponse(db.Model):
    """
    SurveyResponse Model

    Attributes:
        id (Column): Primary key.
        _answers (Column): The answers as JSON, keyed by question (see QUESTIONS).
        _user_id (Column): The respondent's account, when they were logged in.
        created_at (Column): When it was sent.
    """
    __tablename__ = 'survey_responses'

    # Question keys the survey form sends, with the short label admins see
    QUESTIONS = {
        'fit_goals': 'Fits Sesh goals',
        'easy_fun': 'Easy and fun',
        'enjoy': 'Best-fit feature',
        'easier_changes': 'Accessibility changes',
        'accuracy': 'Keeping info accurate',
        'features': 'Top three features',
        'features_other': 'Other feature',
        'why_three': 'Why those three',
        'meme': 'Favorite meme',
        'fav_color': 'Favorite color',
        'notes': 'Additional notes',
    }
    MAX_ANSWER_CHARS = 2000

    id = db.Column(db.Integer, primary_key=True)
    _answers = db.Column(db.Text, nullable=False)
    _user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __init__(self, answers, user=None):
        self._answers = json.dumps(self.clean(answers))
        self._user_id = user.id if user else None

    @classmethod
    def clean(cls, answers):
        """ Keep only known questions; trim text and lists so one response can't flood the table """
        cleaned = {}
        for key in cls.QUESTIONS:
            value = answers.get(key)
            if isinstance(value, list):
                value = [str(v).strip()[:255] for v in value if str(v).strip()][:10]
            elif value is not None:
                value = str(value).strip()[:cls.MAX_ANSWER_CHARS]
            if value:
                cleaned[key] = value
        return cleaned

    def create(self):
        db.session.add(self)
        db.session.commit()
        return self

    def read(self):
        from model.user import User
        user = db.session.get(User, self._user_id) if self._user_id else None
        return {
            "id": self.id,
            "answers": json.loads(self._answers or '{}'),
            "user": user.name if user else "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def initSurveys():
    """ Create the survey_responses table """
    with app.app_context():
        db.create_all()
