"""
Imagination Engine — Living Mind
Category: Synthesis

Hypothetical off-chain predictions. It allows the Brain to simulate the consequences
of potential actions without committing those events to the permanent Memory (cortexDB).
"""

import json
import aiohttp
from cortex.engine import cortex

from core.llm_client import generate as llm_generate, MODEL

class ImaginationEngine:
    def __init__(self):
        self.total_simulations = 0
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def imagine(self, scenario: str) -> str:
        """
        Ask the LLM to predict the outcome of a hypothetical scenario based on identity.
        """
        identity = await cortex.identity_summary()
        prompt = (
            f"You are the inner imagination simulation of a digital runtime.\n"
            f"Current Identity: {identity}\n\n"
            f"SCENARIO TO SIMULATE:\n{scenario}\n\n"
            f"TASK: Predict the most likely outcome of this scenario. What would happen?\n"
            f"Respond concisely in 2 sentences."
        )
        outcome = await self._call_llm(prompt)
        if outcome:
            outcome = self._parse_outcome(outcome)
            self.total_simulations += 1
        return outcome or "Simulation failed."

    def _parse_outcome(self, text: str) -> str:
        cleaned = text.strip().replace("```json", "").replace("```", "").strip("`").strip()
        try:
            data = json.loads(cleaned)
            return data.get("outcome", cleaned)
        except:
            return cleaned

    async def what_if(self, memory_id: str, counterfactual: str) -> str:
        """
        Given a specific memory, simulate what would have happened if a key 
        detail was replaced by the counterfactual string.
        """
        # Fetch the target memory directly via a custom query since ID fetch isn't explicitly exposed on Cortex
        async with cortex._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT content, emotion FROM memories WHERE id = $1", memory_id)
        
        if not row:
            return "Cannot simulate: Initial memory not found."
            
        original_content = row["content"]
        original_emotion = row["emotion"]
        
        prompt = (
            f"You are the counterfactual imagination engine.\n"
            f"ORIGINAL EVENT:\n{original_content} (Emotion: {original_emotion})\n\n"
            f"COUNTERFACTUAL CHANGE:\n{counterfactual}\n\n"
            f"TASK: If this change had occurred, how would the event have played out differently? How would the emotional outcome change?\n"
            f"Respond concisely in 2 sentences."
        )
        
        outcome = await self._call_llm(prompt)
        if outcome:
            outcome = self._parse_outcome(outcome)
            self.total_simulations += 1
        return outcome or "Simulation failed."

    async def _call_llm(self, prompt: str) -> str | None:
        session = await self._get_session()
        return await llm_generate(prompt, temperature=0.7, max_tokens=2048, session=session)

# Module-level singleton
imagination = ImaginationEngine()
