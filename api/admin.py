""" Admin pages served by the backend itself (same home and login pages as Open Coding Society flask)

Uses a signed Flask session cookie, separate from the frontend's JWT cookie, and only lets Admin users in.
"""
from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, session

from model.contact import ContactMessage
from model.survey import SurveyResponse
from model.news import NewsArticle
from model.user import User


admin = Blueprint('admin', __name__)


def current_admin():
    ''' The admin logged in to the backend pages, or None '''
    user = User.query.filter_by(_uid=session.get('admin_uid')).first() if session.get('admin_uid') else None
    # A password change (token_version bump) or losing the Admin role ends the session
    if user is None or not user.is_admin() or session.get('token_version') != user.token_version:
        return None
    return user


@admin.app_context_processor
def inject_current_user():
    return {"current_user": current_admin()}


def admin_required(func):
    @wraps(func)
    def decorated(*args, **kwargs):
        if current_admin() is None:
            return redirect(url_for('admin.login', next=request.path))
        return func(*args, **kwargs)
    return decorated


def safe_next(next_page):
    # Only redirect within this site, never to another domain
    if next_page and next_page.startswith('/') and not next_page.startswith('//'):
        return next_page
    return url_for('index')


@admin.route('/login', methods=['GET', 'POST'])
def login():
    next_page = request.values.get('next', '')
    error = None
    if request.method == 'POST':
        login_id = request.form.get('username', '').strip().lower()
        user = User.query.filter((User._uid == login_id) | (User._email == login_id)).first()
        if user is None or not user.is_password(request.form.get('password', '')):
            error = 'Invalid username or password'
        elif not user.is_admin():
            error = 'Admin access only'
        else:
            session.clear()
            session['admin_uid'] = user.uid
            session['token_version'] = user.token_version
            return redirect(safe_next(next_page))
    elif current_admin():
        return redirect(safe_next(next_page))
    return render_template('login.html', error=error, next_page=next_page), (401 if error else 200)


@admin.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@admin.route('/users/table2')
@admin_required
def utable():
    columns = [('ID', 'id'), ('Name', 'name'), ('User ID', 'uid'), ('Email', 'email'),
               ('Phone', 'phone'), ('Role', 'role'), ('Created', 'created')]
    rows = [user.read() for user in User.query.order_by(User.id).all()]
    for row in rows:
        row['created'] = (row['created_at'] or '')[:10]
    return render_template('table.html', title='User Management', columns=columns, rows=rows)


@admin.route('/news/')
@admin_required
def news():
    # Synced from Sesh's News page (model/news.py), like the PRC Meetings page
    columns = [('ID', 'id'), ('Date', 'date'), ('Title', 'title'), ('Category', 'category'),
               ('Author', 'author'), ('Featured', 'featured'), ('Active', 'active')]
    rows = []
    for article in NewsArticle.query.order_by(NewsArticle._active.desc(), NewsArticle._position).all():
        row = article.read()
        row['active'] = article._active
        rows.append(row)
    return render_template('table.html', title='News (synced from Sesh)', columns=columns, rows=rows)


@admin.route('/contacts/')
@admin_required
def contacts():
    columns = [('ID', 'id'), ('Name', 'name'), ('Email', 'email'), ('Phone', 'phone'), ('Organization', 'organization'),
               ('Topic', 'topic_label'), ('Message', 'message'), ('Handled', 'handled'), ('Received', 'received')]
    rows = [message.read() for message in ContactMessage.query.order_by(ContactMessage.id.desc()).all()]
    for row in rows:
        row['received'] = (row['created_at'] or '')[:10]
    return render_template('table.html', title='Contact Messages', columns=columns, rows=rows)


@admin.route('/surveys/')
@admin_required
def surveys():
    columns = [('ID', 'id'), ('Received', 'received'), ('Account', 'user')] + \
              [(label, key) for key, label in SurveyResponse.QUESTIONS.items()]
    rows = []
    for response in SurveyResponse.query.order_by(SurveyResponse.id.desc()).all():
        data = response.read()
        row = {'id': data['id'], 'user': data['user'], 'received': (data['created_at'] or '')[:10]}
        for key, value in data['answers'].items():
            row[key] = ', '.join(value) if isinstance(value, list) else value
        rows.append(row)
    return render_template('table.html', title='Survey Responses', columns=columns, rows=rows)
