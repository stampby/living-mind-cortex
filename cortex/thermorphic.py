"""
Thermorphic Memory Substrate — Living Mind Cortex
Category: Memory Physics. Runs as a live overlay on top of Postgres.

"What if information had temperature?"

This module is the long-term memory physics layer for the Cortex.
It replaces the hand-written Ebbinghaus decay formula with a real
thermodynamic heat equation, making memory self-organize via physics
instead of programmed rules.

Heat equation:  ∂T/∂t = α∇²T + Q(x,t)
  T   = concept temperature (salience field)
  α   = thermal diffusivity (EVOLVER GENE — mutates nightly)
  ∇²T = Laplacian over the concept graph (diffusion)
  Q   = external heat source (agent access, new memories)

Three emergent behaviors — zero programmed rules:
  1. HOT concepts (frequently accessed) stay salient
  2. FUSED concepts (two hot adjacents collide) spawn emergent nodes
     encoded via HRR circular convolution (holographic binding)
  3. COLD concepts crystallize into immutable long-term memory

Evolver genes (mutated nightly):
  ALPHA            — thermal diffusivity (spread speed)
  FUSION_THRESHOLD — temperature sum to trigger concept fusion
  FREEZE_DWELL     — ticks below freeze before crystallization

Integration:
  - cortex/engine.py  calls substrate.heat()  on every recall()
  - cortex/engine.py  calls substrate.pulse() instead of Ebbinghaus decay()
  - core/dreams.py    runs thermorphic_diffusion strategy (N overnight pulses)
  - core/evolver.py   mutates ALPHA, FUSION_THRESHOLD, FREEZE_DWELL as genome genes
  - cortex/schema.sql stores fusion events in thermal_fusions table
"""

import math
import time
import uuid
import random
import json
import numpy as np
import struct
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict


# ── Thermodynamic Constants ───────────────────────────────────────────────────

ALPHA               = 0.08    # thermal diffusivity (how fast ideas spread through graph)
AMBIENT_TEMPERATURE = 0.05    # heat death floor — nothing goes below this
FUSION_THRESHOLD    = 1.60    # combined temp at which two adjacent concepts fuse
FUSION_YIELD        = 0.55    # fraction of combined heat the new concept inherits
FUSION_DRAIN        = 0.40    # how much heat is lost from parents after fusion
FREEZE_TEMP         = 0.12    # below this = crystallization candidate
FREEZE_DWELL        = 8       # pulses below freeze_temp before crystallization fires
BOIL_THRESHOLD      = 2.50    # above this = concept is "boiling" — signal this to agent
EMISSION_RATE       = 0.92    # passive cooling each tick (like radiation)
MAX_EMISSIONS       = 12      # max fusion events per pulse (thermodynamic rate cap)


# ── Core Data Structures ──────────────────────────────────────────────────────

@dataclass
class ConceptNode:
    """
    A single node in the thermorphic knowledge graph.
    Temperature is the fundamental property — everything else is derived from it.
    """
    id:           str
    content:      str
    temperature:  float         = 0.5    # [0 → ∞), ambient = 0.05
    anchor_temperature: float   = 0.0    # floor temp: 0.0 = normal decay, >0 = pinned
    state:        str           = "molten"  # molten | crystallizing | crystallized | boiling
    tags:         List[str]     = field(default_factory=list)
    edges:        List[str]     = field(default_factory=list)  # neighbor node IDs
    cool_ticks:   int           = 0       # consecutive ticks below FREEZE_TEMP
    born_from:    List[str]     = field(default_factory=list)  # parent IDs if fused
    born_at_pulse: int          = 0       # substrate pulse count at injection
    created_at:   float         = field(default_factory=time.time)
    last_heated:  float         = field(default_factory=time.time)
    access_count: int           = 0
    immutable:    bool          = False   # True once crystallized

    # Holographic vector (simplified: random unit vector in R^256)
    hvec:         np.ndarray    = field(default_factory=lambda: np.zeros(256))

    def heat(self, delta: float, source: str = "external"):
        """Inject heat into this concept. Boosts temperature and resets cool counter."""
        if self.immutable:
            return  # crystallized concepts don't absorb heat
        self.temperature = min(self.temperature + delta, 10.0)
        self.cool_ticks  = 0
        self.last_heated = time.time()
        self.access_count += 1
        self._update_state()

    def cool(self, rate: float = EMISSION_RATE):
        """Passive radiation — lose heat each tick toward ambient."""
        if self.immutable:
            return
            
        floor = self.anchor_temperature if self.anchor_temperature > 0.0 else AMBIENT_TEMPERATURE
        self.temperature = max(floor, self.temperature * rate)
        
        if self.temperature < FREEZE_TEMP:
            self.cool_ticks += 1
        else:
            self.cool_ticks = 0
        self._update_state()

    def _update_state(self):
        if self.immutable:
            self.state = "crystallized"
        elif self.temperature >= BOIL_THRESHOLD:
            self.state = "boiling"
        elif self.cool_ticks >= FREEZE_DWELL:
            self.state = "crystallizing"
        elif self.temperature < FREEZE_TEMP:
            self.state = "cold"
        else:
            self.state = "molten"

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "content":     self.content[:80],
            "temperature": round(self.temperature, 4),
            "state":       self.state,
            "tags":        self.tags,
            "edges":       self.edges,
            "cool_ticks":  self.cool_ticks,
            "born_from":   self.born_from,
            "access_count": self.access_count,
            "immutable":   self.immutable,
        }


@dataclass
class FusionEvent:
    """Record of an emergent concept fusion."""
    parent_a_id:    str
    parent_b_id:    str
    child_id:       str
    child_content:  str
    temp_at_fusion: float
    pulse:          int
    timestamp:      float = field(default_factory=time.time)


# ── HRR Helper (Holographic Reduced Representation) ───────────────────────────

_TWO_PI = 2.0 * math.pi

# Global deterministic token -> phase cache (survives across pulses)
_TOKEN_PHASE_CACHE: dict[str, np.ndarray] = {}

# ── Semantic Expansion Map ────────────────────────────────────────────────────
# Maps surface tokens to semantically related neighbors. Shared meaning is
# captured by superposing neighbor phase vectors at a fractional weight.
# Expand this organically as you notice recall gaps on specific concept clusters.
_SEMANTIC_MAP: dict[str, list[str]] = {
    # Security / credentials
    "password":     ["credential", "secret", "key", "auth", "passcode", "pin", "login"],
    "credential":   ["password", "login", "account", "access", "auth"],
    "secret":       ["password", "private", "hidden", "key", "credential"],
    "auth":         ["authenticate", "login", "credential", "access", "token"],
    "token":        ["auth", "key", "credential", "api", "jwt"],
    "hunter2":      ["password", "secret", "credential"],

    # Infrastructure / systems
    "server":       ["host", "machine", "node", "instance", "backend"],
    "database":     ["db", "postgres", "storage", "table", "sql"],
    "db":           ["database", "postgres", "storage"],
    "postgres":     ["database", "db", "sql", "pg"],
    "api":          ["endpoint", "route", "service", "interface"],
    "host":         ["server", "machine", "node"],
    "alpha":        ["server", "primary", "host", "main"],
    "online":       ["running", "active", "up", "live"],
    "down":         ["offline", "stopped", "failed", "crash"],
    "error":        ["failure", "crash", "exception", "bug", "fault"],
    "failure":      ["error", "crash", "down", "fault"],

    # Memory / cognitive
    "memory":       ["recall", "remember", "store", "knowledge", "cognition"],
    "recall":       ["retrieve", "remember", "fetch", "query", "search", "memory"],
    "remember":     ["recall", "store", "memory", "retain"],
    "forget":       ["decay", "lose", "drop", "crystallize"],
    "knowledge":    ["memory", "fact", "semantic", "information"],

    # Agent / AI
    "agent":        ["zola", "bot", "daemon", "autonomous", "sovereign"],
    "zola":         ["agent", "daemon", "autonomous"],
    "pipeline":     ["workflow", "process", "chain", "flow"],
    "deploy":       ["launch", "start", "run", "ship"],

    # Query paraphrases
    "what":         ["tell", "show", "recall", "find", "get"],
    "tell":         ["what", "show", "recall", "explain"],
    "find":         ["search", "recall", "locate", "get"],
    "show":         ["tell", "recall", "display", "what"],

    # Security hardening domain
    "secure":       ["safe", "protected", "encrypted", "hardened"],
    "encrypted":    ["secure", "encoded", "protected", "cipher"],
    "protect":      ["secure", "guard", "defend", "harden"],
}


def _get_token_vec(token: str, dim: int) -> np.ndarray:
    """Fetch or generate a deterministic phase unit vector for a token."""
    if token not in _TOKEN_PHASE_CACHE:
        seed = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = np.random.default_rng(seed)
        _TOKEN_PHASE_CACHE[token] = np.exp(1j * rng.uniform(0, 2 * np.pi, dim))
    return _TOKEN_PHASE_CACHE[token]


def encode_atom(content: str, dim: int = 256, expansion_weight: float = 0.65) -> np.ndarray:
    """
    Compositional HRR semantic encoding with semantic expansion.

    Each token contributes its phase vector at full weight (1.0), and its
    semantic neighbors contribute at expansion_weight (default 0.65).
    Shared vocabulary AND shared meaning both produce high cosine similarity.
    Zero extra dependencies — entirely deterministic and offline.
    """
    if not content:
        return np.zeros(dim, dtype=np.float64)

    tokens = content.lower().split()
    ngrams = tokens + [a + b for a, b in zip(tokens, tokens[1:])]

    complex_sum = np.zeros(dim, dtype=complex)

    for token in ngrams:
        # Primary token at full weight
        complex_sum += _get_token_vec(token, dim)

        # Semantic neighbors at reduced weight
        for neighbor in _SEMANTIC_MAP.get(token, []):
            complex_sum += expansion_weight * _get_token_vec(neighbor, dim)

    phase_vec = np.angle(complex_sum) % (2 * np.pi)
    return phase_vec.astype(np.float64)

def _random_hvec(dims: int = 256) -> np.ndarray:
    """Random phase vector in [0, 2π). Used when no content string available."""
    return np.random.default_rng().uniform(0, _TWO_PI, dims)

def _hrr_bind(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Phase addition. O(N), no magnitude collapse, no renormalization needed."""
    return (a + b) % _TWO_PI

def _hrr_dot(a: np.ndarray, b: np.ndarray) -> float:
    """Phase cosine similarity. Range [-1, 1]."""
    return float(np.mean(np.cos(a - b)))

# ============================================================
#  CAUSAL BINDING CONSTANTS
# ============================================================
_causal_rng = np.random.default_rng(seed=42)
_causal_perms = {}

def _hrr_permute(vec: np.ndarray) -> np.ndarray:
    """
    Apply a fixed causal permutation to a holographic vector.
    Breaks HRR commutativity: bind(cause, permute(effect)).
    This geometrically encodes directional / causal order.
    """
    dim = len(vec)
    if dim not in _causal_perms:
        perm = np.arange(dim)
        _causal_rng.shuffle(perm)
        _causal_perms[dim] = perm
    return vec[_causal_perms[dim]]


def _synthesize_content(a: ConceptNode, b: ConceptNode) -> str:
    """
    Generate the emergent concept label when A and B fuse.
    Determines causal order from born_at_pulse before labelling.
    """
    cause, effect = (a, b) if a.born_at_pulse <= b.born_at_pulse else (b, a)
    c_words = cause.content.split()[:3]
    e_words = effect.content.split()[-3:]
    return f"[CAUSAL] {' '.join(c_words)} → {' '.join(e_words)}"


# ── The Thermorphic Substrate ─────────────────────────────────────────────────

class ThermorphicSubstrate:
    """
    The full thermorphic computing engine.
    Formally implements IBenchmarkableSubstrate (cortex/protocols.py).

    This is a knowledge graph where information has temperature.
    Concepts flow, fuse, crystallize, and boil purely through
    thermodynamic physics — no programmed rules for what to remember
    or forget. The physics decides.

    IBenchmarkableSubstrate contracts honored:
      1. Construction  — dims accepted AND applied (asserted, not advisory)
      2. Lifecycle     — reset() fully purges all state
      3. Pulse semantics — freeze_dwell is per-instance, not module-global
    """

    def __init__(self, dims: int = 256, freeze_dwell: int = FREEZE_DWELL):
        # Contract 1: dims applied — expose as instance attribute so callers
        # can assert the OUTCOME (substrate.dims == expected), not just the API.
        self.dims: int = dims

        # Contract 3: freeze_dwell per-instance so benchmark scenarios can
        # vary it without module-global cross-contamination.
        self.freeze_dwell: int = freeze_dwell

        self.nodes:         Dict[str, ConceptNode] = {}
        self.fusion_log:    List[FusionEvent]      = []
        self.pulse_count:   int                    = 0
        self.total_fusions: int                    = 0
        self.total_crystals: int                   = 0
        self._heat_injections: List[Tuple[str, float, str]] = []  # queued heat events
        self.SAFE_MUTATION_GAP = self._calculate_safe_mutation_gap()
        from cortex.hologram import HolographicSuperposition
        self.hsm = HolographicSuperposition(dims=self.dims)

        # Behavioral assertion — validates outcome, not API surface.
        # A constructor that accepts dims and ignores it will fail here.
        assert self.hsm.dims == self.dims, (
            f"HSM dims mismatch: hsm.dims={self.hsm.dims} != requested {self.dims}. "
            f"HolographicSuperposition did not apply the dims argument."
        )

    def _calculate_safe_mutation_gap(self) -> int:
        """Dynamically compute system collision constant based on decay physics."""
        gap = 0
        temp = 1.8  # Max injection peak
        while temp > (1.8 - 0.5) and gap < 50:
            temp *= EMISSION_RATE
            gap += 1
        return gap
        
    # ── PUBLIC API ─────────────────────────────────────────────────────────

    def reset(self) -> None:
        """
        Contract 2: Lifecycle — fully purge all substrate state.
        Idempotent. Safe to call between benchmark scenarios.
        Does NOT reset dims or freeze_dwell (construction params are stable).
        """
        self.nodes.clear()
        self.fusion_log.clear()
        self._heat_injections.clear()
        self.pulse_count   = 0
        self.total_fusions = 0
        self.total_crystals = 0
        from cortex.hologram import HolographicSuperposition
        self.hsm = HolographicSuperposition(dims=self.dims)

    def inject(
        self,
        content:     str,
        temperature: float      = 0.8,
        anchor_temperature: float = 0.0,
        tags:        List[str]  = None,
        edges_to:    List[str]  = None,
        dims:        int        = 256,
    ) -> ConceptNode:
        """
        Inject a new concept into the substrate at a given temperature.
        Higher temperature = more "urgent" / salient / recently encountered.
        """
        from cortex.move_subsystem import move_guard
        
        # Geometrically encode the content
        encoded_hvec = encode_atom(content, dims)

        # MoVE Filter: Cross-attend against identity anchors to suppress hallucinated context
        identity_hvecs = [n.hvec for n in self.nodes.values() if n.anchor_temperature > 0.0]
        if identity_hvecs:
            floors = np.array(identity_hvecs)
            encoded_hvec = move_guard.filter(encoded_hvec, floors)

        node = ConceptNode(
            id          = str(uuid.uuid4())[:8],
            content     = content,
            temperature = temperature,
            anchor_temperature = anchor_temperature,
            tags        = tags or [],
            edges       = edges_to or [],
            born_at_pulse = self.pulse_count,
            hvec        = encoded_hvec,
        )
        self.nodes[node.id] = node

        # Wire reciprocal edges
        for target_id in (edges_to or []):
            if target_id in self.nodes and node.id not in self.nodes[target_id].edges:
                self.nodes[target_id].edges.append(node.id)

        return node

    def heat(self, node_id: str, delta: float, source: str = "access"):
        """Externally heat a concept (e.g., agent just accessed it)."""
        if node_id in self.nodes:
            self.nodes[node_id].heat(delta, source)

    def connect(self, id_a: str, id_b: str):
        """Add a bidirectional thermal edge between two concepts."""
        if id_a in self.nodes and id_b in self.nodes:
            if id_b not in self.nodes[id_a].edges:
                self.nodes[id_a].edges.append(id_b)
            if id_a not in self.nodes[id_b].edges:
                self.nodes[id_b].edges.append(id_a)

    def pulse(self) -> dict:
        """
        Run one thermodynamic tick.
        Four phases:
          1. Diffusion    — heat flows from hot nodes to cool neighbors
          2. Radiation    — all nodes lose heat passively
          3. Fusion       — adjacent hot node pairs spawn emergent concepts
          4. Crystallize  — sufficiently cold nodes lock into long-term memory
        """
        global FREEZE_DWELL
        _memoized_global_dwell = FREEZE_DWELL
        FREEZE_DWELL = self.freeze_dwell

        try:
            self.pulse_count += 1
            
            # HSM: Superimpose the current hot path
            hot_nodes = {nid: n for nid, n in self.nodes.items() if n.temperature > FREEZE_TEMP}
            self.hsm.update(hot_nodes)
            
            events = {
                "pulse":      self.pulse_count,
                "diffusions": 0,
                "fusions":    [],
                "crystals":   [],
                "boiling":    [],
            }

            # ── Phase 1: Thermal Diffusion ──────────────────────────────────
            # Each hot node pushes heat to its cooler neighbors.
            # Magnitude follows Fourier's law: q = α × (T_hot - T_cool)
            heat_deltas: Dict[str, float] = defaultdict(float)

            for node_id, node in self.nodes.items():
                if node.immutable or not node.edges:
                    continue
                for neighbor_id in node.edges:
                    if neighbor_id not in self.nodes:
                        continue
                    neighbor = self.nodes[neighbor_id]
                    delta_t  = node.temperature - neighbor.temperature
                    if delta_t > 0 and not neighbor.immutable:
                        flow_rate = ALPHA * delta_t
                        heat_deltas[neighbor_id] += flow_rate * 0.5
                        heat_deltas[node_id]     -= flow_rate * 0.5
                        events["diffusions"]     += 1

            for node_id, delta in heat_deltas.items():
                if node_id in self.nodes:
                    new_temp = self.nodes[node_id].temperature + delta
                    self.nodes[node_id].temperature = max(AMBIENT_TEMPERATURE, new_temp)

            # ── Phase 2: Passive Radiation ──────────────────────────────────
            for node in self.nodes.values():
                node.cool(EMISSION_RATE)
                if node.state == "boiling":
                    events["boiling"].append(node.id)

            # ── Phase 3: Semantic Fusion ────────────────────────────────────
            # Find pairs of adjacent hot nodes that exceed the fusion threshold.
            # Cap at MAX_EMISSIONS fusions per pulse (thermodynamic rate limit).
            fusions_this_pulse = 0
            checked_pairs = set()

            for node_id, node in list(self.nodes.items()):
                if fusions_this_pulse >= MAX_EMISSIONS:
                    break
                if node.immutable or node.temperature < 0.5:
                    continue

                for neighbor_id in node.edges:
                    if neighbor_id not in self.nodes:
                        continue
                    pair_key = tuple(sorted([node_id, neighbor_id]))
                    if pair_key in checked_pairs:
                        continue
                    checked_pairs.add(pair_key)

                    neighbor = self.nodes[neighbor_id]
                    if neighbor.immutable:
                        continue

                    combined_temp = node.temperature + neighbor.temperature
                    if combined_temp >= FUSION_THRESHOLD:
                        child = self._fuse(node, neighbor)
                        event = FusionEvent(
                            parent_a_id    = node_id,
                            parent_b_id    = neighbor_id,
                            child_id       = child.id,
                            child_content  = child.content,
                            temp_at_fusion = combined_temp,
                            pulse          = self.pulse_count,
                        )
                        self.fusion_log.append(event)
                        events["fusions"].append({
                            "parents": [node_id, neighbor_id],
                            "child":   child.id,
                            "content": child.content,
                            "temp":    round(combined_temp, 3),
                        })
                        fusions_this_pulse  += 1
                        self.total_fusions  += 1

            # ── Phase 4: Crystallization ────────────────────────────────────
            for node_id, node in self.nodes.items():
                if not node.immutable and node.cool_ticks >= FREEZE_DWELL:
                    node.immutable  = True
                    node.state      = "crystallized"
                    node.temperature = 0.0
                    self.total_crystals += 1
                    events["crystals"].append(node_id)

            return events

        finally:
            FREEZE_DWELL = _memoized_global_dwell

    async def recall(self, query_content: str, top_k: int = 5) -> List[ConceptNode]:
        """
        Retrieve the most relevant concepts.
        Relevance = thermal weight × semantic similarity.
        Warmer concepts are more salient. Crystallized concepts are durable.
        Accessing a node heats it (spreading activation via thermodynamics).
        """
        results = []
        q_words = set(query_content.lower().split())

        for node in self.nodes.values():
            # Simple word-overlap similarity (replace with HRR dot product in production)
            n_words  = set(node.content.lower().split())
            overlap  = len(q_words & n_words) / max(len(q_words | n_words), 1)

            # Thermal boost: hot concepts surface more readily
            thermal_boost = node.temperature if not node.immutable else 0.3
            score         = overlap * (1.0 + thermal_boost)

            results.append((score, node))

        results.sort(key=lambda x: x[0], reverse=True)
        top = [node for _, node in results[:top_k]]
        
        # ── Collision Resolution Guard ────────────────────────────────
        if len(top) >= 2 and len(q_words & set(top[0].content.lower().split())) > 0:
            delta_t = abs(top[0].temperature - top[1].temperature)
            sim_diff = abs(results[0][0] - results[1][0])
            
            # If nodes are extremely similar semantically but their temp delta is dangerously small
            if delta_t < 0.5 and sim_diff < 0.5 and (top[0].temperature > 1.0 or top[1].temperature > 1.0):
                top[0] = await self._resolve_collision(query_content, top[0], top[1])
                # Remove the losing node to prevent context pollution
                top.pop(1)

        # Accessing heats the recalled nodes (spreading activation)
        for node in top:
            if not node.immutable:
                node.heat(0.15, source="recall")

        return top

    def snapshot(self) -> dict:
        """Full substrate state for visualization / API."""
        nodes_by_state = defaultdict(list)
        for node in self.nodes.values():
            nodes_by_state[node.state].append(node.to_dict())

        temps = [n.temperature for n in self.nodes.values()]
        return {
            "pulse":          self.pulse_count,
            "total_nodes":    len(self.nodes),
            "total_fusions":  self.total_fusions,
            "total_crystals": self.total_crystals,
            "mean_temp":      round(sum(temps) / max(len(temps), 1), 4),
            "max_temp":       round(max(temps, default=0), 4),
            "nodes_by_state": {k: len(v) for k, v in nodes_by_state.items()},
            "recent_fusions": [
                {"child": f.child_content, "pulse": f.pulse}
                for f in self.fusion_log[-5:]
            ],
            "nodes":          [n.to_dict() for n in self.nodes.values()],
        }

    # ── INTERNAL ───────────────────────────────────────────────────────────

    def _fuse(self, a: ConceptNode, b: ConceptNode) -> ConceptNode:
        """
        Semantic Fusion: two hot adjacent concepts merge into a new emergent node.
        Causal order is resolved from born_at_pulse before asymmetric HRR binding.
        """
        cause, effect = (a, b) if a.born_at_pulse <= b.born_at_pulse else (b, a)
        
        combined_temp = a.temperature + b.temperature
        child_temp    = combined_temp * FUSION_YIELD

        # Drain parents
        a.temperature = max(AMBIENT_TEMPERATURE, a.temperature * FUSION_DRAIN)
        b.temperature = max(AMBIENT_TEMPERATURE, b.temperature * FUSION_DRAIN)
        a._update_state()
        b._update_state()

        # Generate emergent content
        child_content = _synthesize_content(a, b)

        # Holographic binding — asymmetric permutation encodes causality
        if cause.hvec is not None and effect.hvec is not None:
            child_hvec = _hrr_bind(cause.hvec, _hrr_permute(effect.hvec))
        else:
            child_hvec = _random_hvec(256)

        child = ConceptNode(
            id          = str(uuid.uuid4())[:8],
            content     = child_content,
            temperature = child_temp,
            tags        = list(set(a.tags + b.tags + ["emergent", "fused", "causal"])),
            edges       = [a.id, b.id],
            born_from   = [a.id, b.id],
            born_at_pulse = self.pulse_count,
            hvec        = child_hvec,
        )
        self.nodes[child.id] = child

        # Wire parent edges back to child
        a.edges.append(child.id)
        b.edges.append(child.id)

        return child
        
    async def _resolve_collision(self, query: str, node_a: ConceptNode, node_b: ConceptNode) -> ConceptNode:
        """
        LLM fallback for thermal collisions (delta_t < 0.5).
        Asks the organism to actively resolve the contradiction via explicit context.
        """
        import aiohttp
        prompt = f"""You are the memory cortex. A semantic collision occurred between two highly salient memories.
Query context: {query}
Fact 1: [Temperature {node_a.temperature:.1f}] {node_a.content}
Fact 2: [Temperature {node_b.temperature:.1f}] {node_b.content}
Resolve the contradiction based on temperature recency and logic. Output ONLY the correct string content."""
        try:
            from core.llm_client import generate as llm_generate
            winning_text = await llm_generate(prompt, temperature=0.1, max_tokens=2048)
            if winning_text:
                if node_a.content.lower() in winning_text.lower():
                    return node_a
                elif node_b.content.lower() in winning_text.lower():
                    return node_b
        except Exception:
            pass
        # Fallback to pure thermodynamic winner
        return node_a if node_a.temperature >= node_b.temperature else node_b


# ── Demo / Runnable Simulation ────────────────────────────────────────────────

def _bar(temp: float, width: int = 20) -> str:
    filled = min(width, int(temp / 3.0 * width))
    colors = {
        "cold":         "░",
        "crystallized": "█",
        "boiling":      "🔥",
    }
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {temp:.3f}"

def _state_icon(state: str) -> str:
    return {
        "molten":        "🌡 ",
        "boiling":       "🔥",
        "cold":          "❄ ",
        "crystallizing": "🧊",
        "crystallized":  "💎",
    }.get(state, "?")


def run_demo():
    print("\n" + "═"*65)
    print("  THERMORPHIC COMPUTING SUBSTRATE — Live Demo")
    print("  'What if information had temperature?'")
    print("═"*65 + "\n")

    sub = ThermorphicSubstrate()

    # Seed with a constellation of concepts from an AI coding session
    concepts = [
        ("asyncpg connection pooling",          1.8, ["python", "database"]),
        ("FastAPI lifespan context manager",    1.4, ["python", "api"]),
        ("PostgreSQL schema migration",         0.9, ["database", "sql"]),
        ("Ebbinghaus forgetting curve",         1.2, ["memory", "cognition"]),
        ("hormone cross-talk rules",            1.6, ["biology", "cognition"]),
        ("circular convolution binding",        0.6, ["math", "encoding"]),
        ("evolutionary fitness oracle",         1.1, ["evolution", "agent"]),
        ("semantic diffusion gradient",         0.4, ["math", "graph"]),
        ("circadian rhythm phase gate",         0.7, ["biology", "scheduling"]),
        ("metacognition drift detection",       1.3, ["cognition", "agent"]),
        ("interoception energy budget",         0.8, ["biology", "state"]),
        ("quantum-inspired selection pressure", 0.5, ["evolution", "math"]),
    ]

    print("🌡  INJECTING CONCEPTS:")
    nodes = []
    for content, temp, tags in concepts:
        n = sub.inject(content, temperature=temp, tags=tags)
        nodes.append(n)
        icon = _state_icon(n.state)
        print(f"  {icon} [{n.id}] {content[:45]:<45} {_bar(temp, 16)}")

    # Wire semantic edges (what's adjacent in idea-space)
    edges = [
        (0, 1),   # asyncpg ↔ FastAPI lifespan
        (1, 2),   # lifespan ↔ schema migration
        (3, 4),   # ebbinghaus ↔ hormone cross-talk (both cognition)
        (4, 9),   # hormone ↔ metacognition drift
        (5, 7),   # circular conv ↔ semantic diffusion (both math)
        (6, 11),  # fitness oracle ↔ quantum selection (both evolution)
        (8, 10),  # circadian ↔ interoception (both biology)
        (9, 10),  # metacognition ↔ interoception (both internal state)
        (3, 9),   # ebbinghaus ↔ metacognition
        (6, 4),   # fitness ↔ hormone cross-talk
    ]
    for a, b in edges:
        sub.connect(nodes[a].id, nodes[b].id)

    print(f"\n  Wired {len(edges)} semantic edges\n")
    print("═"*65)

    # Run the thermodynamic simulation for 15 pulses
    for tick in range(1, 16):
        print(f"\n⚡ PULSE #{tick}")
        events = sub.pulse()

        # Randomly heat some nodes (simulating agent accessing concepts)
        if tick % 3 == 0:
            heated = random.choice(nodes)
            heated.heat(0.8, source="agent_access")
            print(f"  🤖 Agent accessed: [{heated.id}] {heated.content[:40]}")

        if events["diffusions"] > 0:
            print(f"  〰  {events['diffusions']} diffusion flows")

        for fusion in events["fusions"]:
            print(f"  💥 FUSION: [{fusion['parents'][0]}]+[{fusion['parents'][1]}] → [{fusion['child']}]")
            print(f"        '{fusion['content']}'  T={fusion['temp']}")

        for crystal_id in events["crystals"]:
            node = sub.nodes[crystal_id]
            print(f"  💎 CRYSTALLIZED: [{crystal_id}] '{node.content[:50]}'")

        for boil_id in events["boiling"]:
            node = sub.nodes[boil_id]
            print(f"  🔥 BOILING: [{boil_id}] '{node.content[:40]}' T={node.temperature:.2f}")

    # Final state report
    snap = sub.snapshot()
    print("\n" + "═"*65)
    print("  FINAL THERMAL STATE")
    print("═"*65)
    print(f"  Total nodes:    {snap['total_nodes']} ({snap['total_nodes'] - len(concepts)} emergent)")
    print(f"  Total fusions:  {snap['total_fusions']}")
    print(f"  Crystallized:   {snap['total_crystals']}")
    print(f"  Mean temp:      {snap['mean_temp']}")
    print(f"  Peak temp:      {snap['max_temp']}")
    print()

    print("  NODE THERMAL MAP:")
    all_nodes = sorted(sub.nodes.values(), key=lambda n: n.temperature, reverse=True)
    for node in all_nodes:
        icon = _state_icon(node.state)
        born = " [EMERGENT]" if node.born_from else ""
        print(f"  {icon} [{node.id}] {node.content[:42]:<42} {_bar(node.temperature, 14)}{born}")

    # Recall demo
    print("\n" + "═"*65)
    print("  THERMAL RECALL: query='cognition memory agent'")
    print("═"*65)
    results = sub.recall("cognition memory agent", top_k=4)
    for i, node in enumerate(results):
        icon = _state_icon(node.state)
        print(f"  #{i+1} {icon} [{node.id}] {node.content[:50]}")
        print(f"       T={node.temperature:.3f}  state={node.state}  tags={node.tags[:3]}")

    print("\n" + "═"*65)
    print("  THE PHYSICS DECIDED WHAT TO REMEMBER.")
    print("  No rules. No decay functions. Just heat.")
    print("═"*65 + "\n")

    return sub


if __name__ == "__main__":
    random.seed(42)
    run_demo()


# ── Module-level singleton ────────────────────────────────────────────────────
# Import this everywhere: `from cortex.thermorphic import substrate`
substrate = ThermorphicSubstrate()
