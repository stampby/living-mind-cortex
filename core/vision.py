"""
Vision Organ — Living Mind
Category: Perception
Analyzes images and screenshots using a local multimodal LLM (moondream).
"""

import base64
import json
import aiohttp

class VisionOrgan:
    def __init__(self):
        self.total_analyzed = 0
        self.model = "Qwen3-VL-4B-Instruct-GGUF"
        self.api_url = "http://localhost:13305/api/v1/chat/completions"

    async def analyze_image(self, image_path: str, prompt: str = "Describe what you see in this screenshot in detail.") -> str:
        """Reads an image from disk and sends it to Lemonade vision model."""
        try:
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            return f"Vision Error: Could not read image at {image_path}. {e}"

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ]}],
            "max_tokens": 2048,
            "temperature": 0.2,
            "stream": False,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.total_analyzed += 1
                        choices = data.get("choices", [])
                        if choices:
                            return choices[0].get("message", {}).get("content", "").strip()
                        return ""
                    else:
                        err = await resp.text()
                        return f"Vision Error: LLM API returned {resp.status} - {err}"
        except Exception as e:
            return f"Vision Error: Connection to LLM failed. {e}"

vision = VisionOrgan()
