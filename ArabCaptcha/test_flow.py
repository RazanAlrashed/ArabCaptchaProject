import httpx
import json
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Challenge, ReferenceWord

BASE_URL = "http://localhost:8000"
API_KEY = "demo_secret_key"
DOMAIN = "http://localhost"

print("--- 1. Testing POST /sessions ---")
res = httpx.post(f"{BASE_URL}/sessions", json={
    "api_key": API_KEY,
    "domain": DOMAIN,
    "signals_json": '{"mouse_moves": 50, "keystrokes": 10}'
})
print("Status:", res.status_code)
session_data = res.json()
print("Response:", json.dumps(session_data, indent=2))
session_id = session_data.get("session_id")
assert session_id, "Session ID missing"

print("\n--- 2. Testing POST /challenges ---")
res = httpx.post(f"{BASE_URL}/challenges", json={
    "session_id": session_id
})
print("Status:", res.status_code)
challenge_data = res.json()
print("Response:", json.dumps(challenge_data, indent=2))
challenge_id = challenge_data.get("challenge_id")
assert challenge_id, "Challenge ID missing"

print("\n--- 3. Testing POST /challenges/{id}/solve (Success Case) ---")
engine = create_engine("sqlite:///./arabcaptcha.db")
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()
chal = db.query(Challenge).filter(Challenge.challenge_id == challenge_id).first()
ref_word = db.query(ReferenceWord).filter(ReferenceWord.word_id == chal.ref_word_id).first()
correct_text = ref_word.correct_text
db.close()

print(f"Correct target for this challenge is: {correct_text}")
res = httpx.post(f"{BASE_URL}/challenges/{challenge_id}/solve", json={
    "ref_answer": correct_text,
    "low_conf_answer": "تجربة إجابة",
    "response_time_ms": 1200,
    "signals_json": '{"paste": false}'
})
print("Status:", res.status_code)
print("Response:", json.dumps(res.json(), indent=2))

print("\n--- 4. Testing GET /words (Admin) ---")
res = httpx.get(f"{BASE_URL}/words")
print("Status:", res.status_code)
print("Returned words count:", len(res.json()))

print("\n✅ All tests passed!")
