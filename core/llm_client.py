"""
LLM Client — Living Mind Cortex (Strix Halo Integration)

Centralized LLM interface replacing all Ollama calls.
Routes to Lemonade Server (llama.cpp) via OpenAI-compatible API.

"I'll be back." — T-800
"""

import aiohttp

# Lemonade Server (llama.cpp backend) — OpenAI-compatible
LLM_BASE_URL = "http://localhost:13305/api/v1"
MODEL = "Qwen3.5-35B-A3B-GGUF"
TIMEOUT = 120


async def generate(prompt: str, temperature: float = 0.3, top_p: float = 0.9,
                   max_tokens: int = 2048, session: aiohttp.ClientSession = None) -> str | None:
    """
    Send a prompt to Lemonade/llama.cpp and return the text response.
    Translates from Ollama-style prompt to OpenAI chat/completions format.
    """
    close_after = False
    if session is None:
        session = aiohttp.ClientSession()
        close_after = True

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "stream": False,
    }

    try:
        async with session.post(
            f"{LLM_BASE_URL}/chat/completions",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            choices = data.get("choices", [])
            if not choices:
                return None
            msg = choices[0].get("message", {})
            text = msg.get("content", "")
            # Handle Qwen3.5 reasoning_content
            if not text and "reasoning_content" in msg:
                text = msg["reasoning_content"]
            return text.strip() if text else None
    except Exception as e:
        print(f"[LLM_CLIENT] Call failed: {type(e).__name__} - {e}")
        return None
    finally:
        if close_after:
            await session.close()
