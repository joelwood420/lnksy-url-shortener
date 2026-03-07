# Lnksy — URL Shortener

A full-stack URL shortener with user accounts, click tracking, and QR code generation.

🔗 **Live app:** [lnksy.fly.dev](https://lnksy.fly.dev)

---

## Features

- **Shorten any URL** — generates a unique 3character shortcode
- **QR code generation** — every short link comes with a downloadable/copyable QR code
- **User accounts** — register and log in to get personalised short URLs (`/<user_id>/<shortcode>`)
- **My Links dashboard** — view all your links, click counts, and page titles in one place
- **Delete links** — remove any of your own shortened URLs
- **Guest shortening** — works without an account; re-uses existing shortcodes for duplicate URLs
- **Auto page title** — scrapes and stores the title of the destination page

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Vite |
| Backend | Python, Flask |
| Database | SQLite |
| Auth | Session-based (bcrypt password hashing) |
| Deployment | Fly.io (Docker) |
| Testing | pytest |

---

## Screenshots

![web main](screenshots/hero.png)

![mobile landing page](screenshots/mobile.png)

![Mobile results](screenshots/mobile-2.png)

---

## Local Setup

### Prerequisites

- Python 3.11+
- Node.js 18+

### 1. Clone the repo

```bash
git clone https://github.com/joelwood420/url_short.git
cd url_short
```

### 2. Build the frontend

```bash
cd url-short
npm install
npm run build
cd ..
```

This generates the `url-short/dist/` folder that Flask will serve.

### 3. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file inside `backend/`:

```bash
echo "secret_key=your-secret-key-here" > .env
```

Start the Flask server:

```bash
python3 app.py
```

Open `http://localhost:5001` in your browser — Flask serves both the API and the React frontend.

> **Frontend development:** If you're making changes to the React code, run `npm run dev` in the `url-short/` directory for hot reloading on `http://localhost:5173`. Vite proxies all API calls back to the Flask server on port 5001.

### 4. Run tests

From the project root:

```bash
pytest
```

---

## Project Structure

```
url_short/
├── backend/
│   ├── app.py            # Flask app & all API routes
│   ├── user_auth.py      # Registration, login, bcrypt helpers
│   ├── schema.sql        # SQLite schema
│   ├── requirements.txt  # Python dependencies
│   └── tests/
│       ├── fixtures.py   # pytest fixtures
│       └── test_app.py   # Test suite
├── url-short/            # React + Vite frontend
│   └── src/
│       ├── api.js        # All fetch calls in one place
│       └── components/
│           ├── Hero.jsx
│           ├── MyUrls.jsx
│           └── Create_User.jsx
├── Dockerfile
├── fly.toml
├── pytest.ini
└── requirements-dev.txt
```

---

## Deployment

The app is containerised with Docker and deployed to [Fly.io](https://fly.io).  
The built React frontend is served as static files by Flask.

```bash
# Build frontend first
cd url-short && npm run build

# Deploy
fly deploy
```

---

## Author

Built by **Joel** · [GitHub](https://github.com/joelwood420)
