""" Survey API: the site's feedback survey (same pattern as api/contact.py) """
from flask import Blueprint, request, jsonify
from flask_restful import Api, Resource

from api.jwt_authorize import token_required, current_user_or_none
from model.survey import SurveyResponse


survey_api = Blueprint('survey_api', __name__, url_prefix='/api')
api = Api(survey_api)


class SurveyAPI:
    class _CRUD(Resource):
        def post(self):
            """ Send survey answers {fit_goals, easy_fun, enjoy, ...}; anyone can respond """
            body = request.get_json(silent=True) or {}
            if not isinstance(body, dict) or not SurveyResponse.clean(body):
                return {"message": "Please answer the survey questions"}, 400
            SurveyResponse(body, current_user_or_none()).create()
            return {"message": "Thanks for your feedback!"}, 201

        @token_required("Admin")
        def get(self):
            """ Admin only: every response, newest first, plus the question labels """
            responses = SurveyResponse.query.order_by(SurveyResponse.created_at.desc()).all()
            return jsonify({
                "questions": [{"key": k, "label": v} for k, v in SurveyResponse.QUESTIONS.items()],
                "responses": [r.read() for r in responses],
            })

    api.add_resource(_CRUD, '/survey')
