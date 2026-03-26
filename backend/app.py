from flask import Flask, redirect, request, jsonify, send_from_directory, session
from flask_wtf.csrf import generate_csrf
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_talisman import Talisman
from dotenv import load_dotenv
import os

from db import initialize_db, close_db, execute_query
from user_auth import (
    create_user,
    authenticate,
    get_user_by_email,
    get_current_user,
    login_session,
    logout_session,
)
from url_service import (
    validate_and_normalise,
    shorten,
    resolve,
    record_click,
    list_urls_for_user,
    delete_url,
    qr_code_for,
)

# ---------------------------------------------------------------------------
# Application bootstrap
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

_docker_static = os.path.join(BASE_DIR, 'frontend', 'dist')
_local_static = os.path.normpath(os.path.join(BASE_DIR, '..', 'frontend', 'dist'))
STATIC_DIR = _docker_static if os.path.isdir(_docker_static) else _local_static

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='')

# --- Secret key validation ---------------------------------------------------
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    raise RuntimeError("SECRET_KEY environment variable is not set. Add it to backend/.env")
if len(app.secret_key) < 32:
    raise RuntimeError(
        f"SECRET_KEY is too short ({len(app.secret_key)} chars). "
        "It must be at least 32 characters. "
        'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
    )

# --- Flask configuration -----------------------------------------------------
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['WTF_CSRF_TIME_LIMIT'] = None
app.config['WTF_CSRF_HEADERS'] = ['X-CSRF-Token']

# --- Security middleware ------------------------------------------------------
Talisman(
    app,
    content_security_policy={
        'default-src': ["'self'"],
        'script-src': ["'self'", "'unsafe-inline'"],
        'style-src': ["'self'", "'unsafe-inline'"],
        'img-src': ["'self'", "data:"],
        'connect-src': ["'self'"],
    },
    force_https=False,
    frame_options='DENY',
    referrer_policy='strict-origin-when-cross-origin',
)

limiter = Limiter(app, default_limits=["100 per day", "10 per minute"])
csrf = CSRFProtect(app)

# --- Database -----------------------------------------------------------------
initialize_db()
app.teardown_appcontext(close_db)



@app.route('/csrf-token', methods=['GET'])
def get_csrf_token():
    token = generate_csrf()
    response = jsonify({"csrf_token": token})
    is_prod = os.environ.get('FLASK_ENV') == 'production'
    response.set_cookie('csrf_token', token, samesite='Lax', secure=is_prod, httponly=False)
    return response


@app.route('/', methods=['GET'])
def render_react():
    return send_from_directory(app._static_folder, 'index.html')


# --- Authentication ----------------------------------------------------------

@app.route('/register', methods=['POST'])
@limiter.limit("3 per minute")
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if get_user_by_email(email):
        return jsonify({"error": "Email already registered"}), 409

    user = create_user(email, password)
    login_session(user)
    return jsonify({"message": "User created successfully", "email": user.email}), 201


@app.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = authenticate(email, password)
    if not user:
        return jsonify({"error": "Invalid email or password"}), 401

    login_session(user)
    return jsonify({"message": "Login successful", "email": user.email}), 200


@app.route('/me', methods=['GET'])
def me():
    user = get_current_user()
    return jsonify({"email": user.email if user else None}), 200


@app.route('/logout', methods=['POST'])
def logout():
    logout_session()
    return jsonify({"message": "Logged out"}), 200


# --- URL shortening -----------------------------------------------------------

@app.route('/shorten', methods=['POST'])
def shorten_url():
    data = request.get_json()
    raw_url = data.get('url')
    custom_title = (data.get('title') or '').strip() or None

    if not raw_url:
        return jsonify({"error": "No URL provided"}), 400

    url, validation = validate_and_normalise(raw_url)
    if not validation.valid:
        if validation.error_reason == "dangerous":
            return jsonify({"error": "This URL has been flagged as dangerous"}), 400
        if validation.error_reason == "service_unavailable":
            return jsonify({"error": "URL safety check is unavailable, please try again later"}), 503
        return jsonify({"error": "Please input a valid URL"}), 400

    user = get_current_user()
    result = shorten(
        url,
        user_id=user.id if user else None,
        custom_title=custom_title,
        page_title=validation.title,
    )

    status = 200 if not result.is_new else 201
    return jsonify({"short_url": result.short_url, "qr_code": result.qr_code_base64}), status


# --- Redirect & static -------------------------------------------------------

@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory(os.path.join(app.static_folder, 'assets'), filename)


@app.route('/<int:user_id>/<shortcode>', methods=['GET'])
def handle_user_redirect(user_id, shortcode):
    original_url = resolve(shortcode)
    if not original_url:
        return jsonify({"error": "Shortcode not found"}), 404
    record_click(shortcode)
    return redirect(original_url)


@app.route('/<shortcode>', methods=['GET'])
def handle_redirect(shortcode):
    file_path = os.path.join(app.static_folder, shortcode)
    if os.path.isfile(file_path):
        return send_from_directory(app.static_folder, shortcode)

    original_url = resolve(shortcode)
    if not original_url:
        return jsonify({"error": "Shortcode not found"}), 404
    record_click(shortcode)
    return redirect(original_url)


# --- User URL management ------------------------------------------------------

@app.route('/my-urls', methods=['GET'])
def my_urls():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login to view your URLs"}), 401

    entries = list_urls_for_user(user.id)
    url_list = [
        {
            "original_url": e.original_url,
            "short_code": e.short_code,
            "click_count": e.click_count,
            "title": e.title,
        }
        for e in entries
    ]
    return jsonify({"user_id": user.id, "urls": url_list}), 200


@app.route('/qr/<shortcode>', methods=['GET'])
def get_qr(shortcode):
    qr = qr_code_for(shortcode)
    if qr is None:
        return jsonify({"error": "Shortcode not found"}), 404
    return jsonify({"qr_code": qr}), 200


@app.route('/delete/<shortcode>', methods=['DELETE'])
def delete_url_route(shortcode):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401

    if not delete_url(shortcode, user.id):
        return jsonify({"error": "URL not found or not owned by user"}), 404

    return jsonify({"message": "URL deleted successfully"}), 200



if __name__ == '__main__':
    app.run(debug=False, port=5001)

