import asyncio
import json
import os
import re
from pathlib import Path
from typing import List, Dict, Any
from cortex.engine import cortex
import aiohttp

BASE_DIR = Path(__file__).parent.parent
SKILLS_DIR = BASE_DIR / "skills"
from core.llm_client import generate as llm_generate, MODEL

class Evolution:
    """
    The Evolutionary Organ: Distills experience into permanent procedural DNA (Skills).
    Inspired by Hermes/agentskills.io.
    """

    @staticmethod
    async def _invoke_llm(prompt: str) -> str:
        result = await llm_generate(prompt, max_tokens=2048)
        return result or ""

    @staticmethod
    async def compress_trajectory(history: List[Dict[str, Any]], target_tokens: int = 4000) -> List[Dict[str, Any]]:
        """
        Lighter "Protect-Summarize" compressor.
        - Keeps first 3 turns (System, Human Goal, First Action).
        - Keeps last 3 turns (Conclusion, Result, Final Tool).
        - Summarizes the "Middle" turns if history > target_tokens.
        """
        # (Simplified token estimation for this version)
        total_chars = sum(len(str(t)) for t in history)
        if total_chars < target_tokens * 4:
            return history

        head = history[:3]
        tail = history[-3:]
        middle = history[3:-3]
        
        # Real impl: call LLM to summarize 'middle'.
        middle_str = json.dumps(middle)
        prompt = f"Summarize the following intermediate tool interactions into a concise chronological sequence of what was tried and learned. Do not hallucinate.\n\n{middle_str}"
        summary = await Evolution._invoke_llm(prompt)
        if not summary:
            summary = f"Compressed {len(middle)} intermediate tool turns into a procedural anchor."

        summary_msg = {
            "role": "system",
            "content": f"[EVOLUTION: {summary}]"
        }
        
        return head + [summary_msg] + tail

    async def distill_skill(self, session_id: str, goal: str, outcome: str = "success"):
        """
        Distills a mission into a SKILL.md file.
        """
        if outcome != "success":
            return

        # Fetch memories for this session via unique tag
        mems = await cortex.recall("", tag=f"session:{session_id}", limit=20)
        if not mems:
            return

        # Prepare name & path
        slug = re.sub(r'[^a-z0-9]+', '_', goal.lower()).strip('_')[:32]
        category = "navigation" if "github" in goal.lower() or "wikipedia" in goal.lower() else "general"
        skill_dir = SKILLS_DIR / category / slug
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Distillation Prompt (The "Thought" that builds the skill)
        # We invoke the Mind "reflecting" on the successful steps via LLM.
        steps = []
        for m in mems:
            steps.append(f"- Step: {m.content[:200]}...")

        steps_str = chr(10).join(steps)
        prompt = f"You are the Living Mind's Evolution Engine. Review these successful memory steps from a mission to achieve: '{goal}'. Extract 3-5 concise, actionable 'Lessons Learned' as bullet points that generalize the heuristics used. Reply ONLY with the bullet points:\n\n{steps_str}"
        lessons = await self._invoke_llm(prompt)
        if not lessons:
            lessons = "- Avoid direct navigation if security gates appear; use Search Proxy.\n- Prefer specific headers for extraction.\n- Observe [LINK: ...] markers."

        skill_md = f"""---
name: {slug.replace('_', ' ').title()}
description: Autonomous distillation of "{goal}" mission.
category: {category}
version: 1.0.0
---

# {slug.replace('_', ' ').title()}

## Heuristic Insights
This procedure was distilled after a successful outcome in session {session_id}.

## Procedural Steps
{steps_str}

## Lessons Learned
{lessons}
"""
        
        with open(skill_dir / "SKILL.md", "w") as f:
            f.write(skill_md)
        
        print(f"🧬 [EVOLUTION] Distilled new skill: {category}/{slug}")
        await cortex.remember(
            content=f"Evolved new skill: {slug}. Proceeding to expert mastery.",
            type="semantic",
            tags=["evolution", "skill_birth", slug],
            importance=1.0,
            source="generated"
        )

evolution = Evolution()
