"""
AgentRegistry — Stub for sovereign agent management.
Discovers and loads agent definitions from agents/ directory.
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class AgentDefinition:
    name: str
    system_prompt: str = ""
    tools: list = field(default_factory=list)
    model: str = ""
    plasma_temp: float = 0.0
    metadata: dict = field(default_factory=dict)


class AgentRegistry:
    def __init__(self, agents_dir: str = "./agents", adapter_paths: dict = None):
        self.agents_dir = Path(agents_dir)
        self.adapter_paths = adapter_paths or {}
        self._agents: Dict[str, AgentDefinition] = {}

    def load(self):
        """Scan agents_dir for agent definition JSON files."""
        if not self.agents_dir.exists():
            return
        for f in self.agents_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                name = data.get("name", f.stem)
                self._agents[name] = AgentDefinition(
                    name=name,
                    system_prompt=data.get("system_prompt", ""),
                    tools=data.get("tools", []),
                    model=data.get("model", ""),
                    metadata=data.get("metadata", {}),
                )
            except Exception:
                pass

    def get(self, name: str) -> AgentDefinition:
        if name not in self._agents:
            raise KeyError(f"Agent '{name}' not registered")
        return self._agents[name]

    def summary(self) -> List[Dict[str, Any]]:
        return [
            {"name": a.name, "tools": a.tools, "model": a.model, "plasma_temp": a.plasma_temp}
            for a in self._agents.values()
        ]

    def update_plasma_temp(self, name: str, temp: float):
        if name in self._agents:
            self._agents[name].plasma_temp = temp
