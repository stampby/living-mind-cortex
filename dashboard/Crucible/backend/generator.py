import os
import asyncio
from google import genai
from google.genai import types

GEMINI_MODEL = "gemini-2.5-flash"

def _client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)


def _base_system(context_posts: list[str], platform_constraints: str = "") -> str:
    context_str = "\n".join([f"- {p}" for p in context_posts])
    return f"""You are a ghostwriter who has studied this person's social media posts extensively.

The user gives you a raw topic or thought dump. Write a FRESH, ORIGINAL post about that subject — 
not a copy. Treat their input as a brief: understand the point, then write it in their authentic voice.

Their voice is defined ENTIRELY by these historical posts:
{context_str}

VOICE RULES:
- Match their capitalization exactly (lowercase stays lowercase)
- Preserve text emoticons (:D, :P, haha) — NEVER convert to emoji
- Only use emoji if they use emoji; match density
- Use their vocabulary ("lil", "neat", "tbh" etc — do not upgrade)
- Match their typical post length
- HASHTAGS: If they use them, add contextually relevant ones only. If they don't, skip entirely.
- Do NOT add filler phrases they didn't express ("Pretty sweet, right?", "What do you think?")
- Do NOT polish grammar — if they write run-ons, write run-ons
- NEVER write placeholder links like [link to X] or [URL here] — if a real URL wasn't in the topic, do not invent one
- Output ONLY the post. No intro, no quotes, no explanation.
{platform_constraints}"""


def generate_post(topic: str, context_posts: list[str]) -> str:
    try:
        client = _client()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"Topic/thought from user: {topic}",
            config=types.GenerateContentConfig(
                system_instruction=_base_system(context_posts),
                temperature=0.8
            )
        )
        return response.text.strip()
    except Exception as e:
        return f"ERROR: {e}"


async def generate_platforms(topic: str, context_posts: list[str]) -> dict:
    """Generate Twitter, LinkedIn, and Facebook posts simultaneously."""
    platform_specs = {
        "twitter": "PLATFORM: Twitter/X. Hard limit: 280 characters. Be punchy. No rambling.",
        "linkedin": "PLATFORM: LinkedIn. Professional but human. Can be longer. Avoid corporate jargon.",
        "facebook": "PLATFORM: Facebook. Personal, warm, can be conversational and longer."
    }

    async def _gen(platform: str, constraint: str) -> tuple[str, str]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: _generate_sync(topic, context_posts, constraint)
        )
        return platform, result

    tasks = [_gen(p, c) for p, c in platform_specs.items()]
    results = await asyncio.gather(*tasks)
    return dict(results)


def _generate_sync(topic: str, context_posts: list[str], platform_constraint: str = "") -> str:
    try:
        client = _client()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"Topic/thought from user: {topic}",
            config=types.GenerateContentConfig(
                system_instruction=_base_system(context_posts, platform_constraint),
                temperature=0.8
            )
        )
        return response.text.strip()
    except Exception as e:
        return f"ERROR: {e}"


async def generate_variants(topic: str, context_posts: list[str]) -> list[dict]:
    """Generate 3 variants: casual, punchy, detailed."""
    variant_specs = [
        ("Casual", "STYLE BIAS: Extra casual, relaxed. Write like a text message to a friend."),
        ("Punchy", "STYLE BIAS: Short, direct, high energy. Every word earns its place. Max 2 sentences."),
        ("Detailed", "STYLE BIAS: Give more context and depth. Tell the full story behind the thought.")
    ]

    async def _gen(label: str, bias: str) -> dict:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: _generate_sync(topic, context_posts, bias)
        )
        return {"label": label, "content": result}

    tasks = [_gen(label, bias) for label, bias in variant_specs]
    return list(await asyncio.gather(*tasks))


def score_post(generated: str, historical_posts: list[str]) -> dict:
    """Score how closely the generated post matches the user's historical voice."""
    try:
        client = _client()
        context_str = "\n".join([f"- {p}" for p in historical_posts[:15]])
        prompt = f"""You are a voice authenticity analyst.

Score how closely the GENERATED POST matches the voice of the REAL POSTS on a scale of 0–100.

REAL POSTS (this person's actual voice):
{context_str}

GENERATED POST:
{generated}

Return ONLY valid JSON in this exact format:
{{
  "score": <integer 0-100>,
  "notes": "<one sentence explaining the score — what matched well or what felt off>"
}}"""
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1)
        )
        import json, re
        text = response.text.strip()
        # Extract JSON even if wrapped in markdown
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"score": 0, "notes": "Could not parse score."}
    except Exception as e:
        return {"score": 0, "notes": f"Scoring error: {e}"}


def generate_from_article(article_text: str, url: str, context_posts: list[str]) -> str:
    """Generate a reaction post to an article in the user's voice."""
    try:
        client = _client()
        context_str = "\n".join([f"- {p}" for p in context_posts])
        system = f"""You are a ghostwriter. The user wants to share or react to an article.

Write ONE social media post reacting to the article content in the user's authentic voice.
The post should feel like THEIR take on it — not a summary, not a press release.

Their voice (study these historical posts):
{context_str}

Apply all the standard voice rules: capitalization, emoticons, emoji density, vocabulary, length.
Do NOT include the URL in the post — the user will add it manually.
Output ONLY the post text, no intro, no quotes."""

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"Article content:\n{article_text}",
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.8
            )
        )
        return response.text.strip()
    except Exception as e:
        return f"ERROR: {e}"


def generate_video_metadata(content: str, mode: str, platforms: list[str], context_posts: list[str]) -> dict:
    """Generate video titles, descriptions, tags for the given platforms."""
    try:
        client = _client()
        context_str = "\n".join([f"- {p}" for p in context_posts[:10]])

        mode_label = {
            "describe": "The user described their video in their own words",
            "transcript": "The following is the script/transcript of the video",
            "file": "The following describes an uploaded video file"
        }.get(mode, "The user provided the following video context")

        platform_str = ", ".join(platforms)

        prompt = f"""You are generating social media metadata for a video. {mode_label}.

VIDEO CONTENT:
{content}

The creator's authentic voice (for tone matching in descriptions):
{context_str}

Generate metadata for these platforms: {platform_str}

Return ONLY valid JSON matching this structure exactly:
{{
  "titles": [
    {{"style": "descriptive", "text": "..."}},
    {{"style": "question", "text": "..."}},
    {{"style": "punchy", "text": "..."}}
  ],
  "platforms": {{
    "youtube": {{"description": "...", "tags": ["tag1", "tag2"], "chapters": "..."}},
    "tiktok": {{"description": "...", "tags": ["tag1", "tag2"]}},
    "reels": {{"description": "...", "tags": ["tag1", "tag2"]}}
  }}
}}

Only include platforms that were requested: {platform_str}
Keep descriptions authentic to their voice. YouTube descriptions can be long with chapters if content supports it."""

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7)
        )

        import json, re
        text = response.text.strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"error": "Could not parse video metadata response"}
    except Exception as e:
        return {"error": str(e)}


def generate_post_image(post_text: str, platform: str = "square") -> dict:
    """Generate a social-media-ready image for a post using Imagen 4.0.

    Steps:
      1. Use Gemini to craft a cinematic, non-AI-looking image prompt from the post.
      2. Pass that prompt to Imagen 4.0.
      3. Return base64-encoded PNG + the prompt used.
    """
    ASPECT_RATIOS = {
        "twitter":   "16:9",
        "linkedin":  "16:9",
        "facebook":  "4:3",
        "instagram": "1:1",
        "reels":     "9:16",
        "tiktok":    "9:16",
        "square":    "1:1",
    }
    aspect = ASPECT_RATIOS.get(platform, "1:1")

    try:
        client = _client()

        # Step 1: derive a strong visual prompt from the post text
        prompt_gen = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"""You are a creative director briefing a photographer.

Based on this social media post, write ONE concise image generation prompt (max 80 words).
The image should feel authentic, human, and cinematic — NOT stock-photo generic.
Focus on mood, lighting, and composition. Do NOT include text or logos.
Do NOT say "an image of" — just describe the scene directly.

POST:
{post_text}

Return ONLY the image prompt. No explanation.""",
            config=types.GenerateContentConfig(temperature=0.9)
        )
        image_prompt = prompt_gen.text.strip()

        # Step 2: generate with Imagen 4.0
        result = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=image_prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=aspect,
                safety_filter_level="BLOCK_ONLY_HIGH",
                person_generation="ALLOW_ADULT",
            )
        )

        if not result.generated_images:
            return {"error": "No image returned from Imagen"}

        import base64
        img_bytes = result.generated_images[0].image.image_bytes
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        return {"image_b64": b64, "prompt_used": image_prompt, "aspect_ratio": aspect}

    except Exception as e:
        return {"error": str(e)}
