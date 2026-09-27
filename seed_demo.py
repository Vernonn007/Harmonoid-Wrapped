"""
Seed the database with realistic demo data so the dashboard looks great immediately.
Run once: python seed_demo.py
"""
import sqlite3, random
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "harmonoid_stats.db"

TRACKS = [
    ("Blinding Lights",     "The Weeknd",        "After Hours"),
    ("Levitating",          "Dua Lipa",          "Future Nostalgia"),
    ("As It Was",           "Harry Styles",      "Harry's House"),
    ("Heat Waves",          "Glass Animals",     "Dreamland"),
    ("Stay",                "The Kid LAROI",     "F*CK LOVE 3"),
    ("Industry Baby",       "Lil Nas X",         "MONTERO"),
    ("Bad Habit",           "Steve Lacy",        "Gemini Rights"),
    ("About Damn Time",     "Lizzo",             "Special"),
    ("BREAK MY SOUL",       "Beyoncé",           "Renaissance"),
    ("Running Up That Hill","Kate Bush",         "Hounds of Love"),
    ("Easy On Me",          "Adele",             "30"),
    ("Shivers",             "Ed Sheeran",        "="),
    ("MONTERO",             "Lil Nas X",         "MONTERO"),
    ("Peaches",             "Justin Bieber",     "Justice"),
    ("good 4 u",            "Olivia Rodrigo",    "SOUR"),
    ("drivers license",     "Olivia Rodrigo",    "SOUR"),
    ("Positions",           "Ariana Grande",     "Positions"),
    ("Happier Than Ever",   "Billie Eilish",     "Happier Than Ever"),
    ("Love Story",          "Taylor Swift",      "Fearless (Taylor's Version)"),
    ("Cruel Summer",        "Taylor Swift",      "Lover"),
]

WEIGHTS = [12,10,10,9,8,7,7,6,6,6,5,5,5,4,4,4,4,3,3,3]

conn = sqlite3.connect(DB_PATH)
conn.execute("""
    CREATE TABLE IF NOT EXISTS plays (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, artist TEXT, album TEXT,
        album_art TEXT, started_at TEXT NOT NULL,
        ended_at TEXT, duration_s INTEGER DEFAULT 0,
        source TEXT DEFAULT 'harmonoid'
    )
""")

now = datetime.now()
days = 365
cursor = now - timedelta(days=days)
inserted = 0

while cursor < now:
    hour = cursor.hour
    # Listening probability varies by hour
    if 1 <= hour <= 7:
        prob = 0.02
    elif 8 <= hour <= 10:
        prob = 0.25
    elif 11 <= hour <= 13:
        prob = 0.35
    elif 14 <= hour <= 17:
        prob = 0.30
    elif 18 <= hour <= 22:
        prob = 0.55
    elif hour == 23:
        prob = 0.20
    else:
        prob = 0.10

    if random.random() < prob:
        track = random.choices(TRACKS, weights=WEIGHTS, k=1)[0]
        duration = random.randint(160, 240)
        started  = cursor
        ended    = cursor + timedelta(seconds=duration)
        conn.execute(
            "INSERT INTO plays (title,artist,album,started_at,ended_at,duration_s) VALUES (?,?,?,?,?,?)",
            (track[0], track[1], track[2], started.isoformat(), ended.isoformat(), duration)
        )
        inserted += 1
        cursor = ended + timedelta(seconds=random.randint(5, 120))
    else:
        cursor += timedelta(minutes=random.randint(10, 60))

conn.commit()
conn.close()
print(f"Seeded {inserted} plays over {days} days into {DB_PATH}")
