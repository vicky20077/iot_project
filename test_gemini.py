"""Small Gemini connectivity test. Does not expose the API key."""

from dotenv import load_dotenv
import os

load_dotenv()
key = os.getenv("GEMINI_API_KEY", "").strip()
model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

print("Gemini API key loaded:", bool(key))
print("Gemini model:", model)

if not key:
    raise SystemExit("Add GEMINI_API_KEY to .env first.")

from google import genai

client = genai.Client(api_key=key)
response = client.models.generate_content(
    model=model,
    contents="Reply with exactly: Gemini connection successful.",
)
print(response.text)
