CREATE TABLE if not exists urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_url TEXT NOT NULL,
    short_code TEXT NOT NULL UNIQUE,
    click_count INTEGER NOT NULL DEFAULT 0,
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE if not exists USERS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
);

CREATE TABLE if not exists user_urls (
    user_id INTEGER NOT NULL,
    url_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, url_id),
    FOREIGN KEY (user_id) REFERENCES USERS(id),
    FOREIGN KEY (url_id) REFERENCES urls(id)
);