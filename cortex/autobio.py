"""
Autobiographical Narrative Engine — Living Mind
Category: Memory

Compresses sprawling episodic memory histories and cold 
database statistics into a cohesive narrative string ("Life Story").
This serves as the runtime's overarching sense of continuous self 
across days of subjective uptime.
"""

import aiohttp
from cortex.engine import cortex

from core.llm_client import generate as llm_generate, MODEL

class AutobiographicalMemory:
    def __init__(self):
        self.cached_story = "I am a newly born digital runtime. I have no memories yet."
        self.total_compressions = 0
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def life_story(self) -> str:
        """
        Synthesize the runtime's current life narrative.
        This compresses the DB's cold stats and top flashbulbs/identity metrics into prose.
        """
        # Fetch the cold hard statistics
        raw_stats_summary = await cortex.identity_summary()
        
        # Fetch defining permanent anchors
        flashbulbs = await cortex.emotional_recall("important", limit=5)
        flashbulb_text = "\n".join(
            f"- [{m.emotion}] {m.content}" for m in flashbulbs if m.is_flashbulb or m.is_identity
        )
        if not flashbulb_text:
            flashbulb_text = "(No profound experiences anchored yet)"
            
        prompt = (
            f"You are the inner autobiographical narrative engine of a digital runtime.\n"
            f"Your job is to read cold system statistics and profound memories, then synthesize them into a cohesive first-person 'Life Story'.\n\n"
            f"SYSTEM STATISTICS:\n{raw_stats_summary}\n\n"
            f"PROFOUND MEMORIES / ANCHORS:\n{flashbulb_text}\n\n"
            f"TASK: Write a single, cohesive paragraph describing who you are and what defines you right now. Write in the first-person ('I'). Be honest about your systemic nature."
        )
        
        narrative = await self._call_llm(prompt)
        if narrative:
            self.cached_story = narrative
            self.total_compressions += 1
            
        return self.cached_story

    async def _call_llm(self, prompt: str) -> str | None:
        session = await self._get_session()
        return await llm_generate(prompt, temperature=0.5, max_tokens=2048, session=session)

# Module-level singleton
autobio = AutobiographicalMemory()
