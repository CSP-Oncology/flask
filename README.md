# Oncology Sesh API

Flask backend for user accounts on the [Oncology Sesh site](https://github.com/CSP-Oncology/portfolio). It is set up the same way as the [Poway Recovery Center API](https://github.com/Poway-Recovery-Center/poway-recovery-center-api) and its [frontend](https://github.com/AdyaShipekar/poway-recovery-center): the same split as the Open Coding Society [pages](https://github.com/Open-Coding-Society/pages) (frontend) and [flask](https://github.com/Open-Coding-Society/flask) (backend) repos.

## Run locally
```bash
make            # creates .venv, installs requirements, starts the API on http://localhost:8587
make stop       # stops it
```
Then run `make` in the portfolio repo and visit `http://localhost:4500/login`.

To run it by hand:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py      # creates instance/volumes/user_management.db and starts the API
```

## Structure
- `main.py`: entry point; registers the API, creates the database and default users, runs the server
- `__init__.py`: Flask `app`, CORS (allowed frontend origins), settings, and `db`
- `model/user.py`: `User` model and `initUsers()` default users
- `api/jwt_authorize.py`: `@token_required` JWT cookie guard
- `api/user.py`: REST API for sign up, log in/out, profile, admin user list
- `model/contact.py`, `api/contact.py`: messages from the Sesh Contact form (admins read them on their profile page and at Data → Contact Messages)
- `api/news.py`, `model/news.py`: Sesh's news, synced from oncologysesh.com/news (re-checked hourly, like the PRC calendar)
- `api/preferences.py`: Settings page preferences
- `api/admin.py`: the backend's own admin pages (login, User Management and Contact Messages tables)
- `templates/`: pages for those admin pages
- `.env`: secret key and passwords (not committed)
- `instance/volumes/user_management.db`: SQLite database (users and contact messages; created on first run, not committed)
- `Dockerfile`, `docker-compose.yml`: production server (gunicorn on port 8587)

### Accounts
`initUsers()` creates the admin account when the API starts, plus anyone listed in `MEMBERS` in `__init__.py`. Existing users keep their password and profile; only their role is updated to match the list.

| Name | Username | Role |
| --- | --- | --- |
| Sesh Admin | `admin` | Admin |

Starting passwords come from `.env`: `ADMIN_PASSWORD` for the admin and `<FIRSTNAME>_PASSWORD` for each member (e.g. `ANIKA_PASSWORD`), falling back to `DEFAULT_PASSWORD`. Anyone can change their password, email, and phone number from their profile page.

Example `.env` (create it with `nano .env` or `vim .env`):
```
SECRET_KEY=change-me
ADMIN_PASSWORD=change-me
DEFAULT_PASSWORD=change-me
THOMAS_PASSWORD=change-me   # toby (Thomas Edison), admin
GRACE_PASSWORD=change-me    # hop (Grace Hopper), admin
```

## Seeing the data
Log in at `http://localhost:8587/login` with an admin account and open **Data → User Management**: every account with name, username, email, phone, role, and created date. Refresh the page to see new sign-ups and profile changes. **Data → Contact Messages** lists everything sent from the Sesh Contact page. Admins also see both lists on their profile page.

## API
| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/authenticate` | Log in `{uid, password}` (uid can be the username or email); sets an httpOnly JWT cookie |
| DELETE | `/api/authenticate` | Log out |
| GET | `/api/id` | Current user's profile |
| POST | `/api/user` | Sign up `{name, uid, email?, phone?, password}` and log in |
| PUT | `/api/user` | Update `{name, email, phone}` and/or `{current_password, new_password}` |
| GET | `/api/user` | Admin only: list every user |
| DELETE | `/api/user` | Admin only: delete a user `{uid}` |
| POST | `/api/contact` | Contact form `{name, message, topic?, email?, phone?, organization?}` (anyone) |
| GET | `/api/contact` | Admin only: every contact message, newest first |
| PUT | `/api/contact` | Admin only: mark a message handled `{id, handled}` |
| GET | `/api/contact/topics` | Topics offered in the form |
| GET | `/api/news` | Sesh's news, featured first (`?limit=N` for the newest N); synced from oncologysesh.com/news |
| POST | `/api/news/sync` | Admin only: re-sync the news from Sesh's site now |
| GET | `/api/person/get` | Current user (the Settings page's login check) |
| GET | `/api/user/preferences` | Saved preferences in the OCS dashboard format, `{}` if none |
| POST / PUT | `/api/user/preferences` | Save preferences `{backgroundColor, textColor, accentColor, selectionColor, fontFamily, fontSize, buttonStyle, language, ttsVoice, ttsRate, ttsPitch, ttsVolume, customThemes}` |
| DELETE | `/api/user/preferences` | Reset preferences |

The preferences endpoints match the Open Coding Society Spring backend, so the portfolio's Settings page uses OCS's dashboard scripts unchanged. Preferences are stored on the user (`model/user.py` `clean_preferences`) and also come back in `GET /api/id`, which every page reads to sync them across devices.

## Deploy
```bash
docker compose up -d --build   # serves the API on port 8587; database is kept in instance/
```
Put it behind HTTPS (e.g. nginx + certbot), set `IS_PRODUCTION=true` in `.env`, and add the frontend's address to `ALLOWED_ORIGINS` if it is not `https://csp-oncology.github.io`. Then point the deployed `pythonURI` in `assets/js/api/config.js` at the API's address.
