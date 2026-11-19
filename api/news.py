""" News API: Sesh's news, synced from oncologysesh.com/news (same pattern as the PRC schedule API)

All news data lives here; the site's News page and home page only call these endpoints.
"""
from flask import Blueprint, current_app, jsonify, request
from flask_restful import Api, Resource

from api.jwt_authorize import token_required
from model.news import NewsArticle, sync_news, sync_if_stale, sync_status


news_api = Blueprint('news_api', __name__, url_prefix='/api/news')
api = Api(news_api)


def source_info():
    return {
        "source": "Sesh",
        "source_url": current_app.config['NEWS_SOURCE_URL'],
        "last_synced": sync_status["last_synced"],
        "sync_error": sync_status["error"],
    }


class NewsAPI:
    class _List(Resource):
        def get(self):
            """ Sesh's stories, featured first, in Sesh's order; ?limit=N for the newest N """
            sync_if_stale()
            query = NewsArticle.query.filter(NewsArticle._active.is_(True)).order_by(NewsArticle._position)
            try:
                limit = int(request.args.get('limit', 0))
            except ValueError:
                return {"message": "limit must be a number"}, 400
            if limit > 0:
                query = query.limit(limit)
            return jsonify({"articles": [a.read() for a in query.all()], **source_info()})

    class _Sync(Resource):
        @token_required("Admin")
        def post(self):
            """ Admin only: refresh the news from Sesh's site now """
            status = sync_news()
            if status["error"]:
                return {"message": status["error"]}, 502
            return {"message": f"Synced {status['count']} stories", **source_info()}

    api.add_resource(_List, '')
    api.add_resource(_Sync, '/sync')
