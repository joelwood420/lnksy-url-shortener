from flask import Flask, redirect, request, jsonify, send_from_directory, session, g
from dotenv import load_dotenv
import requests
import random
import os
import qrcode
import io
import base64
import ipaddress
from urllib.parse import urlparse
import socket
from bs4 import BeautifulSoup
from db import get_db_connection, initialize_db, close_db, DB_PATH
from user_auth import create_user, get_user_by_email, hash_password, check_password

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

GOOGLE_SAFE_BROWSING_API_KEY = os.environ.get('GOOGLE_SAFE_BROWSING_API_KEY')

_docker_static = os.path.join(BASE_DIR, 'url-short', 'dist')
_local_static = os.path.normpath(os.path.join(BASE_DIR, '..', 'url-short', 'dist'))
STATIC_DIR = _docker_static if os.path.isdir(_docker_static) else _local_static

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='')
app.secret_key = os.environ.get('secret_key')
if not app.secret_key:
    raise RuntimeError("secret_key environment variable is not set. Add it to backend/.env")
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0


initialize_db()

app.teardown_appcontext(close_db)

CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
SHORTCODE_LENGTH = 3


def generate_shortcode():
        return "".join(random.choice(CHARS) for _ in range(SHORTCODE_LENGTH))
    
def execute_query(query, params=()):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = cursor.fetchone() 
    return result


def is_shortcode_unique(generated_shortcode):
    result = execute_query("SELECT 1 FROM urls WHERE short_code = ?", (generated_shortcode,))
    return result is None



def save_url(url, shortcode, user_id=None, title=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO urls (original_url, short_code, title) VALUES (?, ?, ?)", (url, shortcode, title))
    if user_id:
        url_id = cursor.lastrowid
        cursor.execute("INSERT INTO user_urls (user_id, url_id) VALUES (?, ?)", (user_id, url_id))
    conn.commit()


def get_shortcode_for_url(url):
    result = execute_query("SELECT short_code FROM urls WHERE original_url = ?", (url,))
    return result['short_code'] if result else None


def get_shortcode_for_user_url(url, user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT urls.short_code FROM urls
        JOIN user_urls ON urls.id = user_urls.url_id
        WHERE urls.original_url = ? AND user_urls.user_id = ?
    """, (url, user_id))
    result = cursor.fetchone()
    return result['short_code'] if result else None


def get_url_by_shortcode(shortcode):
    result = execute_query("SELECT original_url FROM urls WHERE short_code = ?", (shortcode,))
    return result['original_url'] if result else None


def increment_click_count(shortcode):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE urls SET click_count = click_count + 1 WHERE short_code = ?", (shortcode,))
    conn.commit()
    


def create_short_url(shortcode):
    return f"{request.host_url}{shortcode}"


def is_safe_url(url):
    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return False
        resolved_ip = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(resolved_ip)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
        return True
    except Exception:
        return False


USER_AGENT = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

SAFE_BROWSING_THREAT_TYPES = [
    "MALWARE",
    "SOCIAL_ENGINEERING",
    "UNWANTED_SOFTWARE",
    "POTENTIALLY_HARMFUL_APPLICATION",
]

def is_safe_browsing_url(url):
    """Return False if Google Safe Browsing flags the URL as a known threat."""
    if not GOOGLE_SAFE_BROWSING_API_KEY:
        return True  
    try:
        resp = requests.post(
            "https://safebrowsing.googleapis.com/v4/threatMatches:find",
            params={"key": GOOGLE_SAFE_BROWSING_API_KEY},
            json={
                "client": {"clientId": "url-shortener", "clientVersion": "1.0"},
                "threatInfo": {
                    "threatTypes": SAFE_BROWSING_THREAT_TYPES,
                    "platformTypes": ["ANY_PLATFORM"],
                    "threatEntryTypes": ["URL"],
                    "threatEntries": [{"url": url}],
                },
            },
            timeout=5,
        )
        return resp.status_code != 200 or resp.json() == {}
    except requests.exceptions.RequestException:
        return True  


def is_valid_url(url):
    if not is_safe_url(url):
        return False
    if not is_safe_browsing_url(url):
        return False
    try:
        response = requests.get(url, timeout=5, headers=USER_AGENT, allow_redirects=True)
        return response.status_code < 500
    except requests.exceptions.RequestException:
        return False


def get_page_title(url):
    try:
        response = requests.get(url, timeout=5, headers=USER_AGENT)
        if response.status_code != 200:
            return None
        soup = BeautifulSoup(response.text, 'html.parser')
        title_tag = soup.find('title')
        return title_tag.string.strip() if title_tag and title_tag.string else None
    except Exception:
        return None


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



@app.route('/', methods=['GET'])
def render_react():
    return send_from_directory(app._static_folder, 'index.html')




@app.route('/register', methods=['POST'])
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

    if not original_url:
        return jsonify({"error": "No URL provided"}), 400

    if not original_url.startswith(('http://', 'https://')):
        original_url = 'https://' + original_url

    if not is_valid_url(original_url):
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
        if is_shortcode_unique(shortcode):
            break

    title = get_page_title(original_url)
    save_url(original_url, shortcode, user[0] if user else None, title)
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

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT urls.original_url, urls.short_code, urls.click_count, urls.title
        FROM urls 
        JOIN user_urls ON urls.id = user_urls.url_id 
        WHERE user_urls.user_id = ?
    """, (user[0],))
    urls = cursor.fetchall()

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

    conn = get_db_connection()
    cursor = conn.cursor()
    
    
    cursor.execute("""
        SELECT urls.id FROM urls 
        JOIN user_urls ON urls.id = user_urls.url_id 
        WHERE urls.short_code = ? AND user_urls.user_id = ?
    """, (shortcode, user[0]))
    
    url_record = cursor.fetchone()
    if not url_record:
        return jsonify({"error": "URL not found or not owned by user"}), 404
    

    url_id = url_record[0]
    cursor.execute("DELETE FROM user_urls WHERE url_id = ?", (url_id,))
    cursor.execute("DELETE FROM urls WHERE id = ?", (url_id,))
    
    conn.commit()
    
    return jsonify({"message": "URL deleted successfully"}), 200




if __name__ == '__main__':
    app.run(debug=True, port=5001)

