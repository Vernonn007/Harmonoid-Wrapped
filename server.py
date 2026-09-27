"""
Harmonoid Wrapped — Local stats server
Run: python server.py
Then open: http://localhost:8765
"""

import sqlite3
import json
import http.server
import socketserver
import os
import urllib.request
import urllib.parse
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH      = Path(__file__).parent / "harmonoid_stats.db"
NOW_PATH     = Path(__file__).parent / "now_playing.json"
ARTWORK_DIR  = Path(__file__).parent / "artwork_cache"
PORT         = 8765

ARTWORK_DIR.mkdir(exist_ok=True)

def fetch_artwork_url(artist, title=""):
    """Query iTunes Search API for artwork. Returns a high-res image URL or None."""
    try:
        term = f"{artist} {title}".strip()
        params = urllib.parse.urlencode({
            "term": term,
            "media": "music",
            "limit": 1
        })
        url = f"https://itunes.apple.com/search?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "HarmonoidWrapped/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        results = data.get("results", [])
        if not results:
            # Retry with artist only (no track title) — broader match
            if title:
                params2 = urllib.parse.urlencode({"term": artist, "media": "music", "limit": 1})
                url2 = f"https://itunes.apple.com/search?{params2}"
                req2 = urllib.request.Request(url2, headers={"User-Agent": "HarmonoidWrapped/1.0"})
                with urllib.request.urlopen(req2, timeout=5) as resp2:
                    data2 = json.loads(resp2.read().decode())
                results = data2.get("results", [])
        if not results:
            return None
        art = results[0].get("artworkUrl100", "")
        # Upgrade to higher resolution
        art_hd = art.replace("100x100bb", "600x600bb")
        return art_hd
    except Exception:
        return None

def get_cached_artwork(artist, title=""):
    """Returns local cached file path for artwork, fetching+caching if needed."""
    key = hashlib.md5(f"{artist.lower()}::{title.lower()}".encode()).hexdigest()
    cache_file = ARTWORK_DIR / f"{key}.jpg"
    url_file   = ARTWORK_DIR / f"{key}.url"

    if cache_file.exists():
        return cache_file
    if url_file.exists():
        # Previously failed lookup — don't retry every time
        return None

    art_url = fetch_artwork_url(artist, title)
    if not art_url:
        url_file.write_text("none")
        return None

    try:
        req = urllib.request.Request(art_url, headers={"User-Agent": "HarmonoidWrapped/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            cache_file.write_bytes(resp.read())
        url_file.write_text(art_url)
        return cache_file
    except Exception:
        return None


def query_stats():
    if not DB_PATH.exists():
        return {"error": "No database found. Run tracker.py first."}

    conn = sqlite3.connect(DB_PATH)

    # Totals
    totals = conn.execute("""
        SELECT COUNT(*), COALESCE(SUM(duration_s),0),
               COUNT(DISTINCT artist), COUNT(DISTINCT title)
        FROM plays
    """).fetchone()

    total_plays, total_secs, total_artists, total_tracks = totals
    total_hours = round(total_secs / 3600, 1)
    total_days  = round(total_secs / 86400, 1)

    # Top tracks
    top_tracks = conn.execute("""
        SELECT title, artist, COUNT(*) plays, SUM(duration_s) secs
        FROM plays GROUP BY title, artist
        ORDER BY plays DESC LIMIT 10
    """).fetchall()

    # Top artists
    top_artists = conn.execute("""
        SELECT artist, COUNT(*) plays, SUM(duration_s) secs
        FROM plays GROUP BY artist
        ORDER BY plays DESC LIMIT 10
    """).fetchall()

    # Top albums
    top_albums = conn.execute("""
        SELECT album, artist, COUNT(*) plays
        FROM plays WHERE album != ''
        GROUP BY album ORDER BY plays DESC LIMIT 5
    """).fetchall()

    # Monthly (last 12)
    monthly = conn.execute("""
        SELECT strftime('%Y-%m', started_at) mo,
               COUNT(*) plays,
               ROUND(SUM(duration_s)/3600.0, 1) hours
        FROM plays
        GROUP BY mo ORDER BY mo DESC LIMIT 12
    """).fetchall()
    monthly = list(reversed(monthly))

    # Hourly distribution
    hourly = conn.execute("""
        SELECT CAST(strftime('%H', started_at) AS INTEGER) hr, COUNT(*) cnt
        FROM plays GROUP BY hr ORDER BY hr
    """).fetchall()
    hourly_map = {h: c for h, c in hourly}
    hourly_data = [hourly_map.get(i, 0) for i in range(24)]

    # Day of week
    dow = conn.execute("""
        SELECT CAST(strftime('%w', started_at) AS INTEGER) dow, COUNT(*) cnt
        FROM plays GROUP BY dow ORDER BY dow
    """).fetchall()
    dow_map = {d: c for d, c in dow}
    dow_data = [dow_map.get(i, 0) for i in range(7)]

    # Peak hour
    peak_hour_row = conn.execute("""
        SELECT CAST(strftime('%H', started_at) AS INTEGER) hr, COUNT(*) cnt
        FROM plays GROUP BY hr ORDER BY cnt DESC LIMIT 1
    """).fetchone()
    peak_hour = peak_hour_row[0] if peak_hour_row else 0
    peak_label = f"{peak_hour % 12 or 12} {'AM' if peak_hour < 12 else 'PM'}"

    # Best month
    best_month_row = conn.execute("""
        SELECT strftime('%Y-%m', started_at) mo, COUNT(*) cnt,
               ROUND(SUM(duration_s)/3600.0,1) hrs
        FROM plays GROUP BY mo ORDER BY cnt DESC LIMIT 1
    """).fetchone()
    if best_month_row:
        import calendar
        y, m = best_month_row[0].split('-')
        best_month = calendar.month_name[int(m)]
        best_month_plays = best_month_row[1]
        best_month_hours = best_month_row[2]
    else:
        best_month = "N/A"
        best_month_plays = 0
        best_month_hours = 0

    # Longest streak
    dates = conn.execute("""
        SELECT DISTINCT date(started_at) d FROM plays ORDER BY d
    """).fetchall()
    streak = max_streak = 1
    for i in range(1, len(dates)):
        d1 = datetime.strptime(dates[i-1][0], "%Y-%m-%d")
        d2 = datetime.strptime(dates[i][0],   "%Y-%m-%d")
        if (d2 - d1).days == 1:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 1

    conn.close()

    emojis = ["🌙","🌸","✨","🌊","💜","🎸","🎶","⛰️","🎤","💥"]

    return {
        "totals": {
            "plays":   total_plays,
            "hours":   total_hours,
            "days":    total_days,
            "artists": total_artists,
            "tracks":  total_tracks,
            "streak":  max_streak,
        },
        "top_tracks": [
            {"title": r[0], "artist": r[1], "plays": r[2],
             "secs": r[3], "emoji": emojis[i % len(emojis)]}
            for i, r in enumerate(top_tracks)
        ],
        "top_artists": [
            {"artist": r[0], "plays": r[1], "secs": r[2]}
            for r in top_artists
        ],
        "top_albums": [
            {"album": r[0], "artist": r[1], "plays": r[2]}
            for r in top_albums
        ],
        "monthly":  [{"mo": r[0], "plays": r[1], "hours": r[2]} for r in monthly],
        "hourly":   hourly_data,
        "dow":      dow_data,
        "wrapped": {
            "peak_hour":        peak_label,
            "best_month":       best_month,
            "best_month_plays": best_month_plays,
            "best_month_hours": best_month_hours,
        }
    }

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path == "/control":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                cmd = json.loads(body).get("action", "")
                result = handle_control(cmd)
                data = json.dumps({"ok": result}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", len(data))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/stats":
            data = json.dumps(query_stats()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/recent":
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute("""
                SELECT title, artist, album, started_at, duration_s
                FROM plays
                ORDER BY started_at DESC
                LIMIT 30
            """).fetchall()
            conn.close()
            data = json.dumps([{
                "title": r[0], "artist": r[1], "album": r[2],
                "played_at": r[3], "duration_s": r[4]
            } for r in rows]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
        elif self.path.startswith("/lyrics"):
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            artist = (params.get("artist", [""])[0]).strip()
            title  = (params.get("title",  [""])[0]).strip()
            album  = (params.get("album",  [""])[0]).strip()
            if not artist or not title:
                data = json.dumps({"error": "missing params"}).encode()
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
                return
            try:
                lrc_params = urllib.parse.urlencode({
                    "artist_name": artist,
                    "track_name": title,
                    **({"album_name": album} if album else {})
                })
                lrc_url = f"https://lrclib.net/api/get?{lrc_params}"
                lrc_req = urllib.request.Request(lrc_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
                    "Accept": "application/json",
                    "Referer": "https://lrclib.net/",
                    "Origin": "https://lrclib.net",
                })
                with urllib.request.urlopen(lrc_req, timeout=8) as resp:
                    lrc_data = json.loads(resp.read().decode())
                payload = json.dumps({
                    "synced":  lrc_data.get("syncedLyrics") or "",
                    "plain":   lrc_data.get("plainLyrics")  or "",
                    "title":   lrc_data.get("trackName", title),
                    "artist":  lrc_data.get("artistName", artist),
                    "duration": lrc_data.get("duration", 0),
                }).encode()
            except Exception as e:
                payload = json.dumps({"synced":"","plain":"","error":str(e)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(payload))
            self.end_headers()
            self.wfile.write(payload)
        elif self.path == "/now-playing":
            if NOW_PATH.exists():
                try:
                    payload = NOW_PATH.read_text()
                except Exception:
                    payload = json.dumps({"playing": False})
            else:
                payload = json.dumps({"playing": False})
            data = payload.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/mobile" or self.path == "/mobile/":
            # Serve mobile PWA
            mobile_path = Path(__file__).parent / "mobile.html"
            if mobile_path.exists():
                data = mobile_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", len(data))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
        elif self.path.startswith("/artwork"):
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            artist = (params.get("artist", [""])[0]).strip()
            title  = (params.get("title", [""])[0]).strip()
            if not artist and not title:
                self.send_response(400)
                self.end_headers()
                return
            cache_path = get_cached_artwork(artist, title)
            if cache_path and cache_path.exists():
                img_data = cache_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "public, max-age=604800")
                self.send_header("Content-Length", len(img_data))
                self.end_headers()
                self.wfile.write(img_data)
            else:
                self.send_response(404)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
        else:
            self.path = "/dashboard.html"
            super().do_GET()

    def log_message(self, *args):
        pass

def handle_control(action):
    """Send media commands via Windows keyboard simulation."""
    import ctypes
    VK = {
        "play_pause": 0xB3,
        "next":       0xB0,
        "prev":       0xB1,
        "vol_up":     0xAF,
        "vol_down":   0xAE,
        "vol_mute":   0xAD,
    }
    code = VK.get(action)
    if code is None:
        return False
    # keybd_event: key down then up
    ctypes.windll.user32.keybd_event(code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(code, 0, 2, 0)
    return True

def main():
    os.chdir(Path(__file__).parent)
    # Get local IP for phone access
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "localhost"

    print(f"[SERVER] Harmonoid Wrapped running")
    print(f"[SERVER] Desktop : http://localhost:{PORT}")
    print(f"[SERVER] Phone   : http://{local_ip}:{PORT}/mobile")
    print(f"[SERVER] Press Ctrl+C to stop.\n")
    # Bind to 0.0.0.0 so phone on same WiFi can reach it
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    main()
