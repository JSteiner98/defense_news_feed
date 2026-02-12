import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

print("Fetching model names...")
print("-" * 20)

try:
    # We just want to print the name. No complex filtering.
    for m in client.models.list():
        print(f"Name: {m.name}")
except Exception as e:
    print(f"Error: {e}")