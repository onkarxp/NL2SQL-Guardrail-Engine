import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")
print(f"Key loaded: {api_key[:10]}..." if api_key else "Key NOT loaded — check .env file")
client = Anthropic(api_key=api_key)

response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=100,
    messages=[
        {"role": "user", "content": "Say hello and confirm you can write SQL."}
    ]
)

print(response.content[0].text)