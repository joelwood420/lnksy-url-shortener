from flask import Flask, redirect, request, jsonify, send_from_directory, session
from flask_wtf.csrf import generate_csrf
from dotenv import load_dotenv
import secrets
import os
import sqlite3
import qrcode
import io
import base64
from db import get_db_connection, initialize_db, close_db, DB_PATH, execute_query
from user_auth import create_user, get_user_by_email, hash_password, check_password
from flask_limiter import Limiter
from flask_talisman import Talisman
from url_validation import validate_url_and_get_title
from flask_wtf import CSRFProtect

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

_docker_static = os.path.join(BASE_DIR, 'frontend', 'dist')
_local_static = os.path.normpath(os.path.join(BASE_DIR, '..', 'frontend', 'dist'))
STATIC_DIR = _docker_static if os.path.isdir(_docker_static) else _local_static

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    raise RuntimeError("SECRET_KEY environment variable is not set. Add it to backend/.env")
if len(app.secret_key) < 32:
    raise RuntimeError(
        f"SECRET_KEY is too short ({len(app.secret_key)} chars). "
        "It must be at least 32 characters. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['SESSION_COOKIE_HTTPONLY'] = True   
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['WTF_CSRF_TIME_LIMIT'] = None          # tokens don't expire
app.config['WTF_CSRF_HEADERS'] = ['X-CSRF-Token'] # accept our custom header

Talisman(
    app,
    content_security_policy={
        'default-src': ["'self'"],
        'script-src': ["'self'", "'unsafe-inline'"],   # React needs inline scripts
        'style-src': ["'self'", "'unsafe-inline'"],
        'img-src': ["'self'", "data:"],
        'connect-src': ["'self'"],
    },
    force_https=False,          # handled by the reverse proxy / Fly.io
    frame_options='DENY',       # X-Frame-Options: DENY  (clickjacking)
    referrer_policy='strict-origin-when-cross-origin',
)

limiter = Limiter(app, default_limits=["100 per day", "10 per minute"])

csrf = CSRFProtect(app)

initialize_db()

app.teardown_appcontext(close_db)

CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
SHORTCODE_LENGTH = 5


def generate_shortcode():
        return "".join(secrets.choice(CHARS) for _ in range(SHORTCODE_LENGTH))

def save_url(url, shortcode, user_id=None, title=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN")
        cursor.execute("INSERT INTO urls (original_url, short_code, title) VALUES (?, ?, ?)", (url, shortcode, title))
        if user_id:
            url_id = cursor.lastrowid
            cursor.execute("INSERT INTO user_urls (user_id, url_id) VALUES (?, ?)", (user_id, url_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_shortcode_for_url(url):
    result = execute_query("SELECT short_code FROM urls WHERE original_url = ?", (url,), fetchone=True)
    return result['short_code'] if result else None


def get_shortcode_for_user_url(url, user_id):
    result = execute_query("""
        SELECT urls.short_code FROM urls
        JOIN user_urls ON urls.id = user_urls.url_id
        WHERE urls.original_url = ? AND user_urls.user_id = ?
    """, (url, user_id), fetchone=True)
    return result['short_code'] if result else None


def get_url_by_shortcode(shortcode):
    result = execute_query("SELECT original_url FROM urls WHERE short_code = ?", (shortcode,), fetchone=True)
    return result['original_url'] if result else None


def increment_click_count(shortcode):
    execute_query(
        "UPDATE urls SET click_count = click_count + 1 WHERE short_code = ?",
        (shortcode,), commit=True, fetchone=False
    )


def get_urls_for_user(user_id):
    return execute_query("""
        SELECT urls.original_url, urls.short_code, urls.click_count, urls.title
        FROM urls
        JOIN user_urls ON urls.id = user_urls.url_id
        WHERE user_urls.user_id = ?
    """, (user_id,), fetchall=True)


def delete_url_by_id(url_id, user_id):
    """Delete a URL and its user association. Returns True if a record was deleted."""
    result = execute_query("""
        SELECT urls.id FROM urls
        JOIN user_urls ON urls.id = user_urls.url_id
        WHERE urls.id = ? AND user_urls.user_id = ?
    """, (url_id, user_id), fetchone=True)
    if not result:
        return False
    execute_query("DELETE FROM user_urls WHERE url_id = ?", (url_id,), commit=True, fetchone=False)
    execute_query("DELETE FROM urls WHERE id = ?", (url_id,), commit=True, fetchone=False)
    return True



def create_short_url(shortcode):
    return f"{request.host_url}{shortcode}"


def get_logged_in_user():
    email = session.get('email')
    if not email:
        return None
    return get_user_by_email(email)


def generate_qr_code(short_url):
    qr = qrcode.QRCode(version=1, box_size=12, border=5)
    qr.add_data(short_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#6ecfb0", back_color='#2d2d2d')
    buffer = io.BytesIO()     # Create an in-memory buffer to hold the image data
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode('utf-8') # Return the QR code as string of bytes



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

    password_hash = hash_password(password)
    create_user(email, password_hash)
    session['email'] = email
    return jsonify({"message": "User created successfully", "email": email}), 201



@app.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = get_user_by_email(email)
    if not user or not check_password(password, user[2]):
        return jsonify({"error": "Invalid email or password"}), 401

    session['email'] = email
    return jsonify({"message": "Login successful", "email": email}), 200


@app.route('/me', methods=['GET'])
def me():
    email = session.get('email')
    if not email:
        return jsonify({"email": None}), 200
    return jsonify({"email": email}), 200


@app.route('/logout', methods=['POST'])
def logout():
    session.pop('email', None)
    return jsonify({"message": "Logged out"}), 200


@app.route('/shorten', methods=['POST'])
def shorten_url():
    data = request.get_json()
    original_url = data.get('url')
    custom_title = data.get('title', '').strip() if data.get('title') else None

    if not original_url:
        return jsonify({"error": "No URL provided"}), 400

    if not original_url.startswith(('http://', 'https://')):
        original_url = 'https://' + original_url

    result = validate_url_and_get_title(original_url)
    if not result.valid:
        if result.error_reason == "dangerous":
            return jsonify({"error": "This URL has been flagged as dangerous"}), 400
        if result.error_reason == "service_unavailable":
            return jsonify({"error": "URL safety check is unavailable, please try again later"}), 503
        return jsonify({"error": "Please input a valid URL"}), 400

    user = get_logged_in_user()

    if user:
        existing_shortcode = get_shortcode_for_user_url(original_url, user[0])
        if existing_shortcode:
            short_url = f"{request.host_url}{user[0]}/{existing_shortcode}"
            qr_code = generate_qr_code(short_url)
            return jsonify({"short_url": short_url, "qr_code": qr_code}), 200
    else:
        existing_shortcode = get_shortcode_for_url(original_url)
        if existing_shortcode:
            short_url = create_short_url(existing_shortcode)
            qr_code = generate_qr_code(short_url)
            return jsonify({"short_url": short_url, "qr_code": qr_code}), 200
    while True:
        shortcode = generate_shortcode()
        try:
            save_url(original_url, shortcode, user[0] if user else None, custom_title or result.title)
            break
        except sqlite3.IntegrityError:
            continue
    if user:
        short_url = f"{request.host_url}{user[0]}/{shortcode}"
    else:
        short_url = create_short_url(shortcode)
    qr_code = generate_qr_code(short_url)
    print(f"Short URL: {short_url}")
    response = jsonify({"short_url": short_url, "qr_code": qr_code})
    return response, 201





@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory(os.path.join(app.static_folder, 'assets'), filename)



@app.route('/<int:user_id>/<shortcode>', methods=['GET'])
def handle_user_redirect(user_id, shortcode):
    original_url = get_url_by_shortcode(shortcode)
    if original_url:
        increment_click_count(shortcode)
        return redirect(original_url)
    else:
        return jsonify({"error": "Shortcode not found"}), 404


@app.route('/<shortcode>', methods=['GET'])
def handle_redirect(shortcode):
    file_path = os.path.join(app.static_folder, shortcode)
    if os.path.isfile(file_path):
        return send_from_directory(app.static_folder, shortcode)
    
    original_url = get_url_by_shortcode(shortcode)
    if original_url:
        increment_click_count(shortcode)
        return redirect(original_url)
    else:
        return jsonify({"error": "Shortcode not found"}), 404
    


@app.route('/my-urls', methods=['GET'])
def my_urls():
    user = get_logged_in_user()
    if not user:
        return jsonify({"error": "Login to view your URLs"}), 401

    urls = get_urls_for_user(user[0])
    url_list = [{"original_url": row["original_url"], "short_code": row["short_code"], "click_count": row["click_count"], "title": row["title"]} for row in urls]
    return jsonify({"user_id": user[0], "urls": url_list}), 200




@app.route('/qr/<shortcode>', methods=['GET'])
def get_qr(shortcode):
    original_url = get_url_by_shortcode(shortcode)
    if not original_url:
        return jsonify({"error": "Shortcode not found"}), 404

    short_url = create_short_url(shortcode)
    qr_code = generate_qr_code(short_url)
    return jsonify({"qr_code": qr_code}), 200


@app.route('/delete/<shortcode>', methods=['DELETE'])
def delete_url(shortcode):
    user = get_logged_in_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401

    url_record = execute_query("""
        SELECT urls.id FROM urls
        JOIN user_urls ON urls.id = user_urls.url_id
        WHERE urls.short_code = ? AND user_urls.user_id = ?
    """, (shortcode, user[0]), fetchone=True)
    if not url_record:
        return jsonify({"error": "URL not found or not owned by user"}), 404

    if not delete_url_by_id(url_record["id"], user[0]):
        return jsonify({"error": "URL not found or not owned by user"}), 404

    return jsonify({"message": "URL deleted successfully"}), 200




if __name__ == '__main__':
    app.run(debug=True, port=5001)

