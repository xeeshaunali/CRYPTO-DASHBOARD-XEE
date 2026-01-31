# Crypto Scanner Full Package

This archive contains a complete frontend + backend project for fetching historical OHLCV data using `ccxt`.

Files included:
- index.html (frontend)
- app.py (Flask backend)
- requirements.txt
- start.sh (helper to run server)
- Dockerfile
- README.md
- LICENSE (MIT)

Important:
1. Start the backend before using the frontend.
   ```
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
   ```
2. Open index.html in your browser (double-click) OR serve it (recommended) with a static server.
   Example (Python 3):
   ```
   python -m http.server 8000
   # then open http://127.0.0.1:8000/index.html
   ```
3. The frontend calls the backend at http://127.0.0.1:5000

If Bootstrap appears not to load:
- Ensure your machine has internet access (Bootstrap is loaded from CDN).
- If you prefer fully offline, replace CDN links with local files (not included).

dslkjfsldflskdhflkdsflkdsjf