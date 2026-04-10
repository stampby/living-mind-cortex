"""
TopologyMapper — Living Mind
Spatial Architecture Engine.
Allows the runtime to autonomously structure its 3D visualization topology.
"""

import json
import asyncio
import aiohttp
from datetime import datetime

from core.llm_client import generate as llm_generate, MODEL

class TopologyMapper:
    def __init__(self):
        self.last_census_len = 0
        self.last_inflammation = 0.0
        self.current_topology = None
        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def pulse(self, inflammation: float, runtime_registry: list, mapped_instances: dict) -> dict | None:
        """
        Check if a major structural shift needs to occur.
        If yes, trigger LLM architecture redesign.
        """
        census_len = len(runtime_registry)
        is_shift = False

        if census_len > self.last_census_len:
            is_shift = True 
            print("[TOPOGRAPHER] Structural Shift detected: New organ registered.")
        elif abs(inflammation - self.last_inflammation) > 0.4:
            is_shift = True
            print("[TOPOGRAPHER] Structural Shift detected: Major inflammation change.")
            
        if self.current_topology is None:
            is_shift = True # Initial boot

        self.last_census_len = census_len
        self.last_inflammation = inflammation

        if is_shift:
            new_topo = await self._design_topology(runtime_registry, inflammation)
            if new_topo:
                self._attach_functions(new_topo, mapped_instances)
                self.current_topology = new_topo
                return new_topo
        
        return None

    async def _design_topology(self, registry: list, inflammation: float) -> dict | None:
        """Deterministic Motherboard Chip Layout Generator."""
        
        # Categorize organs into geometric "zones"
        zones = {
            "Consciousness":       {"origin": [0, 0, -300], "slots": []},  # Top Center
            "Perception":          {"origin": [-300, 0, -200], "slots": []},
            "Learning":            {"origin": [300, 0, -200], "slots": []},
            "Cognition":           {"origin": [0, 0, 0], "slots": []},     # CPU Center
            "Synthesis":           {"origin": [350, 0, 0], "slots": []},   # Right flank
            "Memory":              {"origin": [-350, 0, 0], "slots": []},  # Left flank
            "Autonomy/Integration":{"origin": [0, 0, 150], "slots": []},   # Buses below CPU
            "Resilience":          {"origin": [-200, 0, 250], "slots": []},
            "Defense":             {"origin": [200, 0, 250], "slots": []},
            "Structure":           {"origin": [0, 0, 350], "slots": []},   # Bottom Core
            "Social":              {"origin": [500, 0, -300], "slots": []}, # Agent Bridge — upper right
            "Unknown":             {"origin": [300, 0, 300], "slots": []}
        }

        # Assign Organs to Zones
        for r in registry:
            cat = r.get("category", "Unknown")
            if cat not in zones: cat = "Unknown"
            zones[cat]["slots"].append(r["name"])

        nodes = []
        links = []
        
        # Distribute chips within their designated motherbard zones on an iron-clad grid
        for zone, data in zones.items():
            organs = data["slots"]
            ox, _, oz = data["origin"]
            
            # Simple linear distribution spreading within the zone
            spacing = 90
            for i, organ in enumerate(organs):
                # offset horizontally if multiple
                offset_x = ox + (i - len(organs)/2.0 + 0.5) * spacing
                nodes.append({
                    "id": organ,
                    "pos": [offset_x, 0, oz],
                    "category": zone
                })

        # Procedural Logic Traces (Trunk wiring)
        # Connect everything up hierarchically towards the Brain (Cognition) and Cortex (Memory)
        names = [n["id"] for n in nodes]
        for name in names:
            if name != "brain" and "brain" in names:
                links.append([name, "brain"])
            if name != "cortex" and "cortex" in names and name != "brain":
                links.append([name, "cortex"])
            if name == "immune" and "pulse_event" in names:
                links.append(["pulse_event", "immune"])
            # Nodus (agent gateway) bridges to brain and cortex
            if name == "nodus" and "brain" in names:
                links.append(["nodus", "brain"])
            if name == "nodus" and "cortex" in names:
                links.append(["nodus", "cortex"])

        return {"nodes": nodes, "links": links}

    def _attach_functions(self, topo: dict, mapped_instances: dict):
        if not topo or "nodes" not in topo: return
        import inspect
        for n in topo["nodes"]:
            n_id = n.get("id")
            if n_id and n_id in mapped_instances:
                inst = mapped_instances[n_id]
                funcs = []
                for attr_name in dir(inst):
                    if not attr_name.startswith("_"):
                        attr = getattr(inst, attr_name)
                        if callable(attr):
                            funcs.append(attr_name)
                n["functions"] = funcs

topology_mapper = TopologyMapper()
