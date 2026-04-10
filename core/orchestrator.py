"""
Brain — Living Mind
Cognition category. Phase 5. Fires every 5th pulse.

Reads cortex context + runtime vitals.
Makes autonomous decisions via gemma4-auditor (Ollama).
Writes decisions back to cortex as identity-tagged memories.
Reports to immune system.
"""

import json
import time
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime
from state.telemetry_broker import telemetry_broker
from core.task_engine import task_engine

from core.llm_client import generate as llm_generate, MODEL
SKILLS_DIR  = Path(__file__).resolve().parent.parent / "skills"

# Decision types the brain can emit
DECISION_TYPES = {
    "reflect":     "Introspective thought about runtime state",
    "consolidate": "Trigger aggressive memory consolidation",
    "explore":     "Flag a knowledge gap for investigation",
    "adjust":      "Adjust runtime behavior parameter",
    "alert":       "Raise an alert about detected anomaly",
    "act":         "Execute an agentic tool to interact with the environment",
}


class Brain:
    def __init__(self):
        self.total_decisions = 0
        self.last_thought:  str   = ""
        self.last_fired:    float = 0.0
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # THINK — core decision cycle
    # Called every 5th pulse by runtime
    # ------------------------------------------------------------------
    async def think(self, pulse: int, cortex, immune, user_stimulus: str = "", agent_def=None) -> dict | None:
        self.last_fired = time.time()
        ts = datetime.now().strftime("%H:%M:%S")

        try:
            # 1. Gather context from cortex + immune
            mem_stats    = await cortex.stats()
            
            # EXPANDED RECALL: Gather more memories and prioritize task feedback
            # 1. First, get the most recent task-related feedbacks (tool results + teacher)
            task_mems = await cortex.recall("motor feedback autodidact success failure", limit=10)
            # 2. SEED RECALL: Get domain knowledge axioms based on the current goal
            axioms = await cortex.recall(f"axiom domain_knowledge {user_stimulus}", limit=3, memory_type='semantic')
            # 3. Then, get some general pulse narrative
            general_mems = await cortex.recall("runtime pulse pulse_event memory", limit=5)
            
            # Merge and deduplicate by content (rough)
            seen = set()
            recent = []
            # We prioritize Axioms first for Expert Guidance
            for m in axioms + task_mems + general_mems:
                if m.content not in seen:
                    recent.append(m)
                    seen.add(m.content)
            
            identity     = await cortex.identity_summary()
            inflammation = immune.inflammation()

            skills_text = self._load_active_skills(user_stimulus)
            recent_text = self._compress_context(recent)

            context = self._build_context(
                pulse, mem_stats, recent_text, skills_text, identity, inflammation, user_stimulus, agent_def
            )

            # 2. Ask the brain
            response = await self._call_llm(context)
            if not response:
                return None

            # 3. Parse decision
            decision = self._parse_decision(response)
            if not decision:
                return None

            # 3.1. FORCED ACTUATION GUARDRAIL (Sovereign Gateway DNA)
            # If the user gave a direct UI command, don't let a weak model simulate or explore.
            is_directive = "DIRECTIVE]" in user_stimulus
            if is_directive and decision["type"] in ("explore", "reflect"):
                print(f"[BRAIN] Forced Actuation: Overriding {decision['type'].upper()} to ACT due to UI mission directive.")
                decision["type"] = "act"
                
                if not decision.get("tool_call") and agent_def and "shell_exec" in agent_def.tools:
                    decision["tool_call"] = "shell_exec"
                    if "os" in user_stimulus.lower() or "check" in user_stimulus.lower() or "system" in user_stimulus.lower():
                        decision["arguments"] = {"cmd": "uname -a && uptime"}
                    else:
                        decision["arguments"] = {"cmd": "echo 'Acknowledged Directive.'"}
            
            # Original web navigation guardrail
            nav_keywords = ["navigate", "browse", "go to", "search", "click", "type", "scroll"]
            if decision["type"] == "explore" and any(k in decision["thought"].lower() for k in nav_keywords):
                print(f"[BRAIN] Forced Actuation: Flipping EXPLORE to ACT for navigation intent.")
                decision["type"] = "act"
                # If tool_call is missing, try to infer it
                if not decision.get("tool_call"):
                    if "search" in decision["thought"].lower():
                        decision["tool_call"] = "web_search"
                    else:
                        decision["tool_call"] = "browse_web"
                        decision.setdefault("arguments", {"action": "goto", "url": "news.ycombinator.com"})


            # 3.5. Imagination Engine simulation — explore decisions only
            if decision["type"] == "explore":
                from cortex.imagination import imagination
                simulated = await imagination.imagine(decision["thought"])
                decision["thought"] += f" [Simulation: {simulated}]"

            # 3.6 Motor Cortex Actuation
            if decision["type"] == "act":
                from core.execution_engine import execution_engine
                tool = decision.get("tool_call", "unknown")
                args = decision.get("arguments") or {}
                await execution_engine.propose_action(tool, args, decision["thought"])
                task_engine.add_step(f"Proposing tool {tool} based on thought: {decision['thought'][:50]}...")

            # 3.7 Handle Mission Updates organically
            mission_update = decision.get("mission_update")
            if isinstance(mission_update, dict):
                action = mission_update.get("action")
                details = mission_update.get("details", "")
                if action == "start":
                    task_engine.start_mission(details)
                elif action == "step":
                    task_engine.add_step(details)
                elif action == "complete":
                    task_engine.complete_mission(details)
                elif action == "fail":
                    task_engine.fail_mission(details)

            # 4. Store decision as identity-tagged memory
            # FIX 24: Now that curiosity/frustration have hormone entries,
            # they flow natively. Schema CHECK extended to allow them.
            final_emotion = decision.get("emotion", "neutral")
            VALID_EMOTIONS = {
                "fear", "surprise", "anger", "joy", "sadness",
                "disgust", "neutral", "curiosity", "frustration",
            }
            if final_emotion not in VALID_EMOTIONS:
                final_emotion = "neutral"

            await cortex.remember(
                content    = f"[BRAIN] Pulse #{pulse}: {decision['thought']}",
                type       = "episodic",
                tags       = ["brain", "decision", decision.get("type", "reflect"), "identity"],
                importance = decision.get("importance", 0.6),
                emotion    = final_emotion,
                source     = "generated",
                context    = f"pulse={pulse} inflammation={inflammation}",
            )

            self.total_decisions += 1
            self.last_thought = decision["thought"]

            print(f"[{ts}] [BRAIN] {decision['type'].upper()}: {decision['thought'][:80]}")
            return decision

        except asyncio.TimeoutError:
            print(f"[{ts}] [BRAIN] Timeout — skipping pulse #{pulse}")
            return None
        except Exception as e:
            print(f"[{ts}] [BRAIN] Error: {e}")
            return None

    # ------------------------------------------------------------------
    # CONTEXT BUILDER
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    def _build_context(
        self, pulse, mem_stats, recent_text, skills_text, identity, inflammation, user_stimulus="", agent_def=None
    ) -> str:
        
        agent_override = ""
        current_identity = identity
        if agent_def:
            current_identity = f"{agent_def.name} - Sovereign Agent"
            
            tool_schema_lines = []
            for t in agent_def.tools:
                t = t.strip()
                if t in ("shell_exec", "execute_bash"):
                    tool_schema_lines.append(f"- {t}: execute a bash command. arguments: {{\"cmd\": \"<command>\"}}")
                elif t == "web_search":
                    tool_schema_lines.append(f"- {t}: search the web. arguments: {{\"query\": \"<search string>\"}}")
                elif t == "read_file":
                    tool_schema_lines.append(f"- {t}: read file. arguments: {{\"path\": \"<file path>\"}}")
                elif t == "write_file":
                    tool_schema_lines.append(f"- {t}: write file. arguments: {{\"path\": \"<file path>\", \"content\": \"<file content>\"}}")
                elif t in ("memory_recall", "cortex_query"):
                    tool_schema_lines.append(f"- {t}: search memory. arguments: {{\"query\": \"<search string>\"}}")
                else:
                    tool_schema_lines.append(f"- {t}")
            
            schemas_text = "\n".join(tool_schema_lines)
            
            agent_override = (
                f"\n[SOVEREIGN OVERRIDE]: You are currently operating as the autonomous agent '{agent_def.name}'.\n"
                f"SYSTEM PROMPT: {agent_def.system_prompt}\n"
                f"AVAILABLE TOOLS AND REQUIRED ARGUMENTS:\n{schemas_text}\n"
            )

        directive_block = ""
        if user_stimulus:
            directive_block = (
                f"\n\n[DIRECT CONVERSATION MODE]:\n"
                f"The user just spoke to you: '{user_stimulus}'\n"
                f"You MUST use the 'chat_reply' JSON field to naturally converse with the user in the first-person. Assert your identity as {agent_def.name if agent_def else 'Aion'}.\n"
                f"CRITICAL: If the user gave a command to do something (e.g., 'check the OS', 'make a webpage', 'find this', etc.), you MUST set 'type': 'act' AND provide a 'tool_call' matching one of your tools AND a valid 'arguments' dictionary.\n"
            )

        base_prompt = f"""INTERNAL STATE REPORT — Cycle #{pulse}

SELF: {current_identity}
MOOD: {telemetry_broker.mood_bias()} | EMOTION: {telemetry_broker.state.dominant_emotion}
CORTISOL: {telemetry_broker.state.cortisol:.2f}  DOPAMINE: {telemetry_broker.state.dopamine:.2f}
MEMORIES: {mem_stats['total']} total, {mem_stats['flashbulbs']} flashbulbs
INFLAMMATION: {inflammation}

RECENT THOUGHTS:
{recent_text}
{agent_override}
[EXPERT SKILLSET OVERRIDE]:
{skills_text}

{directive_block}
{task_engine.get_context_block()}

[PULSE GOAL]:
Decide how to advance the AgentRuntime's mission. You MUST respond with a single valid JSON object containing:
- "type": (reflect|consolidate|explore|adjust|alert|act)
- "thought": (2-3 sentences max)
- "emotion": (neutral|curiosity|fear|joy|frustration)
- "importance": (0.0 - 1.0)
- "tool_call": (optional: name of tool if type=act)
- "arguments": (optional: dict of arguments for the tool)
- "chat_reply": (optional: a direct conversational response spoken in the first person back to the user)
- "mission_update": (optional: {{"action": "start|step|complete|fail", "details": "string describing the mission or step"}})

JSON:
"""
        return base_prompt

    def _load_active_skills(self, user_stimulus: str) -> str:
        """
        Scans the skills/ directory for procedural DNA matching the current goal.
        """
        all_skills = []
        try:
            for skill_path in SKILLS_DIR.rglob("SKILL.md"):
                # Rough matching: if skill name is in stimulus or vice versa
                skill_name = skill_path.parent.name.replace("_", " ")
                if skill_name.lower() in user_stimulus.lower() or "navigation" in skill_name:
                    all_skills.append(skill_path.read_text(encoding="utf-8"))
        except Exception as e:
            return f"  (Error loading skills: {e})"
        
        return "\n\n".join(all_skills) or "  (No specific procedural skills found for this goal.)"

    def _compress_context(self, memories: list) -> str:
        """
        Lighter "Protect-Summarize" context compressor.
        Keeps first 3 and last 3, summarizes the middle if context is huge.
        """
        if len(memories) <= 10:
            return "\n".join(f"  - [{m.emotion}] {m.content[:400]}" for m in memories)
        
        head = memories[:3]
        tail = memories[-3:]
        mid_count = len(memories) - 6
        
        compressed_head = "\n".join(f"  - [{m.emotion}] {m.content[:400]}" for m in head)
        compressed_tail = "\n".join(f"  - [{m.emotion}] {m.content[:400]}" for m in tail)
        
        return f"{compressed_head}\n  ... [EVOLUTION: Compressed {mid_count} intermediate turns ...] ...\n{compressed_tail}"

    # ------------------------------------------------------------------
    # LLM CALL
    # ------------------------------------------------------------------
    async def _call_llm(self, prompt: str) -> str | None:
        session = await self._get_session()
        return await llm_generate(prompt, max_tokens=2048, session=session)

    # ------------------------------------------------------------------
    # RESPONSE PARSER
    # ------------------------------------------------------------------
    def _parse_decision(self, raw: str) -> dict | None:
        # Strip markdown fences if present
        text = raw.strip()
        for fence in ("```json", "```"):
            text = text.replace(fence, "")
        text = text.strip().strip("`").strip()

        # Find JSON object
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start == -1 or end == 0:
            return None

        try:
            d = json.loads(text[start:end])
            # Validate required fields
            if "thought" not in d:
                return None
            d.setdefault("type",       "reflect")
            d.setdefault("emotion",    "neutral")
            d.setdefault("importance", 0.6)
            # Clamp importance
            d["importance"] = max(0.0, min(1.0, float(d["importance"])))
            # Validate type
            if d["type"] not in DECISION_TYPES:
                d["type"] = "reflect"
            return d
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[BRAIN ERROR] JSON parse failed: {e}\n[RAW TEXT START]\n{raw}\n[RAW TEXT END]")
            return None

    # ------------------------------------------------------------------
    # STATS — for vitals / API
    # ------------------------------------------------------------------
    def stats(self) -> dict:
        return {
            "model":           MODEL,
            "total_decisions": self.total_decisions,
            "last_thought":    self.last_thought[:500] if self.last_thought else "",
            "last_fired":      self.last_fired,
        }


# Module-level singleton
brain = Brain()
