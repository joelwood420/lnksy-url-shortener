from flask import Flask, redirect, request, jsonify, send_from_directory, session
import requests
import random
import os
import sqlite3
import qrcode
import io
import base64
from user_auth import create_user, get_user_by_email, hash_password, check_password

app = Flask(__name__, static_folder='../url-short/dist', static_url_path='')
app.secret_key = os.urandom(24)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0


DB_PATH = 'db/urls.db'
CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
SHORTCODE_LENGTH = 3


def initialize_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as c:
        with open('db/schema.sql', 'r') as f:
            c.executescript(f.read())


initialize_db()

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row

def get_db_connection():
    return conn

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



def save_url(url, shortcode, user_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO urls (original_url, short_code) VALUES (?, ?)", (url, shortcode))
    if user_id:
        url_id = cursor.lastrowid
        cursor.execute("INSERT INTO user_urls (user_id, url_id) VALUES (?, ?)", (user_id, url_id))
    conn.commit()


def get_shortcode_for_url(url):
    result = execute_query("SELECT short_code FROM urls WHERE original_url = ?", (url,))
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


def is_valid_url(url):
    user_agent = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    try:
        response = requests.get(url, timeout=5, headers=user_agent, allow_redirects=True)
        return response.status_code < 500
    except requests.exceptions.RequestException:
        return False


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

    existing_shortcode = get_shortcode_for_url(original_url)

    if existing_shortcode:
        if user:
            short_url = f"{request.host_url}{user[0]}/{existing_shortcode}"
        else:
            short_url = create_short_url(existing_shortcode)
        qr_code = generate_qr_code(short_url)
        print(f"Short URL: {short_url}")
        response = jsonify({"short_url": short_url, "qr_code": qr_code})
        return response, 200
        
        
    while True:
        shortcode = generate_shortcode()
        if is_shortcode_unique(shortcode):
            break

    save_url(original_url, shortcode, user[0] if user else None)
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
        SELECT urls.original_url, urls.short_code, urls.click_count 
        FROM urls 
        JOIN user_urls ON urls.id = user_urls.url_id 
        WHERE user_urls.user_id = ?
    """, (user[0],))
    urls = cursor.fetchall()

    url_list = [{"original_url": row["original_url"], "short_code": row["short_code"], "click_count": row["click_count"]} for row in urls]
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

