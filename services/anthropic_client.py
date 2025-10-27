# services/anthropic_client.py
import os, httpx, asyncio

# Support multiple possible environment variable names for the Anthropic/Claude API key
ANTHROPIC_KEY = (
    os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDEAPI") or os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_KEY")
)
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-opus-20240229")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"  # Messages API endpoint


async def send_to_claude(user_prompt: str, system_prompt: str):
    # Build the messages/prompt that Claude expects (Anthropic uses a specific format)
    prompt = f"{system_prompt}\n\nHuman: {user_prompt}\n\nAssistant:"

    if not ANTHROPIC_KEY:
        # Raise a clear error so the caller can return a helpful JSON response
        raise RuntimeError("Missing ANTHROPIC_API_KEY environment variable")

    # Recent Anthropic API versions require an 'anthropic-version' header.
    headers = {
        "x-api-key": str(ANTHROPIC_KEY),
        "Content-Type": "application/json",
        "anthropic-version": os.getenv("ANTHROPIC_VERSION", "2023-10-01"),
    }
    payload = {
        "model": ANTHROPIC_MODEL,
        "prompt": prompt,
        "max_tokens_to_sample": 800,
        "temperature": 0.7,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Messages API format
            messages_payload = {
                "model": ANTHROPIC_MODEL,
                "messages": [
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 800,
                "temperature": 0.7
            }
            if system_prompt:
                messages_payload["system"] = system_prompt

            r = await client.post(ANTHROPIC_URL, json=messages_payload, headers=headers)
            r.raise_for_status()
            body = r.json()
            # Messages API returns content in message.content
            return body.get("content", [{}])[0].get("text", "")
    except httpx.HTTPStatusError as e:
        # Surface HTTP errors with status and body
        raise RuntimeError(f"Anthropic API error: {e.response.status_code} {e.response.text}")
    except Exception as e:
        raise RuntimeError(f"Anthropic request failed: {e}")
