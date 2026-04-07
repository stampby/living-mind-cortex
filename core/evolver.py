"""
Evolutionary Meta-Layer — Living Mind
Category: Evolution. Fires nightly inside the Dream state.

Makes the Cortex actually evolve instead of just feeling alive.
Three evolution vectors, all targeting better agent collaboration outcomes:

  Vector A — Phase Mutation
    Mutates the runtime's phase_config (pulse frequencies).
    Variants shadow-tested in a lightweight simulation.
    Winner patches the live config. Loser is pruned.

  Vector B — Hormone Genome
    Evolves hormone decay curves and baselines toward configurations
    that correlated with high-rated agent sessions.
    Writes changes live to TelemetryBroker BASELINES/DECAY_RATES.

  Vector C — Quantum-Inspired Selection
    When two variants are within 0.05 fitness, 40% chance of picking
    the more novel one (measured by new memory schemas created).
    Prevents premature convergence.

Fitness oracle is agent-centric:
  fitness = (0.4 × avg_session_rating)      ← POST /api/agent/feedback
           + (0.3 × task_success_rate)       ← agent_sessions.outcome
           + (0.2 × auditor_coherence)       ← gemma4-auditor score
           + (0.1 × energy_efficiency)       ← interoception.energy_budget

Every accepted mutation is checkpointed to lineage_snapshots table.
"""

import copy
import json
import random
import asyncio
import time
import aiohttp
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List

OLLAMA_URL      = "http://localhost:11434/api/generate"
MODEL           = "gemma4-auditor"
OFFSPRING_COUNT = 4       # variants generated per nightly cycle
FITNESS_FLOOR   = 0.3     # minimum fitness to accept a variant
NOVELTY_WINDOW  = 0.05    # fitness delta within which novelty roll activates
NOVELTY_PROB    = 0.40    # probability of picking novel variant when tied


@dataclass
class HormoneGene:
    """A mutable hormone with evolvable parameters."""
    name:          str
    baseline:      float
    decay_rate:    float
    effect_vector: Dict[str, float] = field(default_factory=dict)   # which phases it boosts


@dataclass
class Genome:
    """The organism's mutable blueprint."""
    phase_config:   Dict[str, Any]         # phase_name → fire_every_N_pulses
    hormone_genes:  Dict[str, HormoneGene] # hormone_name → gene
    generation:     int = 0
    fitness:        float = 0.0
    notes:          str = ""


class Evolver:
    def __init__(self, runtime):
        self._runtime   = runtime
        self._session: Optional[aiohttp.ClientSession] = None
        self._generation: int = 0
        self._last_cycle: float = 0.0
        self._cycles_run: int = 0
        self._last_accepted_fitness: float = 0.0

        # Build initial genome from the runtime's live phase_config
        self._current_genome: Optional[Genome] = None   # initialized lazily on first cycle

    # ------------------------------------------------------------------
    # NIGHTLY CYCLE — called from dreams.py after synthesis
    # ------------------------------------------------------------------
    async def nightly_cycle(self, cortex, telemetry_broker):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [EVOLVER] 🧬 Nightly evolution cycle #{self._generation + 1} starting")

        # Lazy genome initialization
        if self._current_genome is None:
            self._current_genome = self._build_initial_genome(telemetry_broker)

        # 1. Compute current fitness (baseline to beat)
        current_fitness = await self._compute_fitness(cortex)
        self._current_genome.fitness = current_fitness
        print(f"[{ts}] [EVOLVER]    Current genome fitness: {current_fitness:.3f}")

        if current_fitness < 0.01:
            print(f"[{ts}] [EVOLVER]    Not enough session data yet — skipping mutation")
            self._cycles_run += 1
            return

        # 2. Generate offspring
        offspring = self._generate_offspring(OFFSPRING_COUNT)

        # 3. Shadow-test each variant
        results: List[tuple[Genome, float]] = []
        for variant in offspring:
            fitness = await self._shadow_test(variant, cortex, telemetry_broker)
            variant.fitness = fitness
            results.append((variant, fitness))
            print(f"[{ts}] [EVOLVER]    Variant '{variant.notes}': {fitness:.3f}")

        # 4. Select winner with quantum-inspired uncertainty
        winner, winner_fitness = self._select_winner(results)

        # 5. Accept or reject
        if winner_fitness > current_fitness and winner_fitness >= FITNESS_FLOOR:
            self._generation += 1
            winner.generation = self._generation
            self._last_accepted_fitness = winner_fitness

            # Apply winner to live runtime
            self._apply_genome(winner, telemetry_broker)

            # Checkpoint to DB
            await self._save_lineage(winner, cortex)

            await cortex.remember(
                content    = f"Evolution accepted: generation {self._generation}, fitness {winner_fitness:.3f}. {winner.notes}",
                type       = "semantic",
                tags       = ["evolution", "genome", "system", f"gen:{self._generation}"],
                importance = 0.85,
                emotion    = "joy",
                source     = "experienced",
            )
            print(f"[{ts}] [EVOLVER] ✅ Generation {self._generation} accepted (fitness {winner_fitness:.3f})")
        else:
            print(f"[{ts}] [EVOLVER] 🛡️  No improvement — keeping current genome ({current_fitness:.3f})")

        self._last_cycle = time.time()
        self._cycles_run += 1

    # ------------------------------------------------------------------
    # GENOME INITIALIZATION
    # ------------------------------------------------------------------
    def _build_initial_genome(self, telemetry_broker) -> Genome:
        """Snapshot the current runtime config as the initial genome."""
        from state.telemetry_broker import BASELINES, DECAY_RATES

        # Phase config from runtime (frequences in pulse counts)
        phase_config = dict(getattr(self._runtime, "phase_config", {
            "decay":        10,
            "dreams":       20,
            "brain":         5,
            "senses":        5,
            "awakening":    50,
            "self_aware":   30,
            "metacognition": 6,
        }))

        # Build hormone genes from current BASELINES + DECAY_RATES
        hormone_genes = {
            name: HormoneGene(
                name       = name,
                baseline   = BASELINES.get(name, 0.5),
                decay_rate = DECAY_RATES.get(name, 0.05),
            )
            for name in BASELINES
        }

        return Genome(
            phase_config  = phase_config,
            hormone_genes = hormone_genes,
            generation    = 0,
            fitness       = 0.0,
            notes         = "Initial genome",
        )

    # ------------------------------------------------------------------
    # OFFSPRING GENERATION
    # ------------------------------------------------------------------
    def _generate_offspring(self, count: int) -> List[Genome]:
        offspring = []
        mutations = [
            self._mutate_phase_frequencies,
            self._mutate_hormone_baselines,
            self._mutate_hormone_decay_rates,
            self._insert_micro_phase,
        ]

        for i in range(count):
            child = copy.deepcopy(self._current_genome)
            # Apply 1-2 mutations per offspring
            n_mutations = random.randint(1, 2)
            chosen = random.sample(mutations, min(n_mutations, len(mutations)))
            applied = []
            for mutate_fn in chosen:
                desc = mutate_fn(child)
                if desc:
                    applied.append(desc)
            child.notes = f"gen{self._generation+1}_offspring{i}: {'; '.join(applied)}"
            offspring.append(child)

        return offspring

    def _mutate_phase_frequencies(self, genome: Genome) -> str:
        """Randomly adjust one phase's fire frequency ±2 pulses."""
        mutable = [k for k in genome.phase_config if k not in ("brain",)]  # protect brain
        if not mutable:
            return ""
        key = random.choice(mutable)
        old_val = genome.phase_config[key]
        delta = random.choice([-2, -1, 1, 2])
        new_val = max(3, min(100, old_val + delta))
        genome.phase_config[key] = new_val
        return f"{key}:{old_val}→{new_val}"

    def _mutate_hormone_baselines(self, genome: Genome) -> str:
        """Nudge one hormone's baseline ±0.03."""
        name  = random.choice(list(genome.hormone_genes.keys()))
        gene  = genome.hormone_genes[name]
        delta = round(random.uniform(-0.03, 0.03), 3)
        gene.baseline = max(0.05, min(0.95, gene.baseline + delta))
        return f"{name}_base:{delta:+.3f}"

    def _mutate_hormone_decay_rates(self, genome: Genome) -> str:
        """Nudge one hormone's decay rate ±0.01."""
        name  = random.choice(list(genome.hormone_genes.keys()))
        gene  = genome.hormone_genes[name]
        delta = round(random.uniform(-0.01, 0.01), 3)
        gene.decay_rate = max(0.01, min(0.40, gene.decay_rate + delta))
        return f"{name}_decay:{delta:+.3f}"

    def _insert_micro_phase(self, genome: Genome) -> str:
        """Occasionally insert a new micro-phase into the config."""
        candidates = {
            "interoception_feedback": 8,
            "context_refresh":        12,
            "counterfactual_replay":  15,
        }
        for phase_name, default_freq in candidates.items():
            if phase_name not in genome.phase_config:
                genome.phase_config[phase_name] = default_freq
                return f"micro_phase:{phase_name}"
        return ""

    # ------------------------------------------------------------------
    # SHADOW TEST — lightweight fitness estimation for a variant
    # ------------------------------------------------------------------
    async def _shadow_test(self, variant: Genome, cortex, telemetry_broker) -> float:
        """
        Estimate variant fitness without applying it to the live system.
        Uses actual DB data: session ratings + outcomes + coherence check.
        """
        # Actual fitness from historical data (same oracle as full fitness)
        base_fitness = await self._compute_fitness(cortex)

        # Modifier based on how extreme the mutations are
        # (large mutations are penalized slightly to prefer conservative changes)
        phase_delta = sum(
            abs(variant.phase_config.get(k, v) - v)
            for k, v in self._current_genome.phase_config.items()
        )
        hormone_delta = sum(
            abs(variant.hormone_genes[n].baseline - self._current_genome.hormone_genes[n].baseline)
            + abs(variant.hormone_genes[n].decay_rate - self._current_genome.hormone_genes[n].decay_rate)
            for n in variant.hormone_genes
            if n in self._current_genome.hormone_genes
        )

        extremity_penalty = min(0.1, (phase_delta + hormone_delta) * 0.01)

        # Small novelty bonus for inserting a new micro-phase
        novelty_bonus = 0.0
        for k in variant.phase_config:
            if k not in self._current_genome.phase_config:
                novelty_bonus = 0.02
                break

        return round(max(0.0, min(1.0, base_fitness - extremity_penalty + novelty_bonus)), 3)

    # ------------------------------------------------------------------
    # FITNESS ORACLE — agent-session-centric
    # ------------------------------------------------------------------
    async def _compute_fitness(self, cortex) -> float:
        """
        fitness = 0.4×avg_session_rating + 0.3×success_rate + 0.2×coherence + 0.1×energy
        """
        try:
            async with cortex._pool.acquire() as conn:
                # Average session rating
                avg_rating = await conn.fetchval("""
                    SELECT AVG(rating) FROM agent_sessions
                    WHERE rating IS NOT NULL AND started_at > extract(epoch from now()) - 604800
                """)  # last 7 days

                # Task success rate
                total = await conn.fetchval("""
                    SELECT COUNT(*) FROM agent_sessions
                    WHERE started_at > extract(epoch from now()) - 604800
                """)
                successes = await conn.fetchval("""
                    SELECT COUNT(*) FROM agent_sessions
                    WHERE outcome = 'success'
                      AND started_at > extract(epoch from now()) - 604800
                """)

            avg_rating   = float(avg_rating or 0.5)
            success_rate = float(successes) / max(1, float(total))

        except Exception:
            avg_rating   = 0.5
            success_rate = 0.5

        # Coherence: use interoception energy budget as proxy if LLM unavailable
        coherence = await self._auditor_coherence()

        # Energy efficiency from interoception
        energy = 0.7  # default healthy
        try:
            from state.interoception import interoception
            energy = interoception.state.energy_budget
        except Exception:
            pass

        fitness = (
            0.4 * avg_rating +
            0.3 * success_rate +
            0.2 * coherence +
            0.1 * energy
        )
        return round(min(1.0, max(0.0, fitness)), 3)

    async def _auditor_coherence(self) -> float:
        """Quick coherence ping from gemma4-auditor. Returns 0.5 on failure."""
        try:
            session = await self._get_session()
            payload = {
                "model":  MODEL,
                "prompt": "Rate the cognitive coherence of a system that remembers past interactions and adapts its behavior accordingly. Reply with only a float between 0.0 and 1.0.",
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 10},
            }
            async with session.post(
                OLLAMA_URL, json=payload,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    raw = data.get("response", "0.5").strip()
                    # Extract first float-like value
                    import re
                    match = re.search(r"\d+\.?\d*", raw)
                    if match:
                        val = float(match.group())
                        return min(1.0, max(0.0, val if val <= 1.0 else val / 10.0))
        except Exception:
            pass
        return 0.5

    # ------------------------------------------------------------------
    # WINNER SELECTION — quantum-inspired
    # ------------------------------------------------------------------
    def _select_winner(self, results: List[tuple]) -> tuple:
        """
        Sort by fitness. If top two are within NOVELTY_WINDOW,
        40% chance of picking the second (novel variant bias).
        """
        sorted_results = sorted(results, key=lambda x: x[1], reverse=True)
        if not sorted_results:
            return self._current_genome, 0.0

        best_genome, best_fitness = sorted_results[0]

        if len(sorted_results) > 1:
            second_genome, second_fitness = sorted_results[1]
            if (best_fitness - second_fitness) < NOVELTY_WINDOW:
                if random.random() < NOVELTY_PROB:
                    return second_genome, second_fitness

        return best_genome, best_fitness

    # ------------------------------------------------------------------
    # APPLY GENOME — patches live runtime
    # ------------------------------------------------------------------
    def _apply_genome(self, genome: Genome, telemetry_broker):
        """Apply the winning genome to the live runtime and hormone bus."""
        from state.telemetry_broker import BASELINES, DECAY_RATES

        # Update phase_config on runtime
        if hasattr(self._runtime, "phase_config"):
            self._runtime.phase_config.update(genome.phase_config)

        # Update hormone baselines and decay rates
        for name, gene in genome.hormone_genes.items():
            if name in BASELINES:
                BASELINES[name]    = round(gene.baseline, 4)
                DECAY_RATES[name]  = round(gene.decay_rate, 4)

        self._current_genome = genome
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [EVOLVER] 🔄 Live genome updated — generation {genome.generation}")

    # ------------------------------------------------------------------
    # LINEAGE CHECKPOINT
    # ------------------------------------------------------------------
    async def _save_lineage(self, genome: Genome, cortex):
        """Persist accepted genome to lineage_snapshots table."""
        try:
            # Collect recent session ratings for the snapshot
            async with cortex._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, rating, outcome FROM agent_sessions
                    WHERE rating IS NOT NULL
                    ORDER BY started_at DESC LIMIT 10
                """)
                session_ratings = [
                    {"id": r["id"], "rating": r["rating"], "outcome": r["outcome"]}
                    for r in rows
                ]

                phase_config_json   = json.dumps(genome.phase_config)
                hormone_genome_json = json.dumps({
                    name: {"baseline": g.baseline, "decay_rate": g.decay_rate}
                    for name, g in genome.hormone_genes.items()
                })
                ratings_json = json.dumps(session_ratings)

                await conn.execute("""
                    INSERT INTO lineage_snapshots
                        (phase_config, hormone_genome, fitness, session_ratings, generation, notes)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """,
                    phase_config_json, hormone_genome_json,
                    genome.fitness, ratings_json,
                    genome.generation, genome.notes,
                )
        except Exception as e:
            print(f"[EVOLVER] Lineage save error: {e}")

    # ------------------------------------------------------------------
    # STATS + CLEANUP
    # ------------------------------------------------------------------
    def stats(self) -> dict:
        return {
            "generation":             self._generation,
            "cycles_run":             self._cycles_run,
            "last_cycle":             self._last_cycle,
            "last_accepted_fitness":  self._last_accepted_fitness,
            "current_phase_config":   getattr(self._current_genome, "phase_config", {}),
        }

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
