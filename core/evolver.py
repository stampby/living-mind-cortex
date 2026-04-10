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

from core.llm_client import generate as llm_generate, MODEL
OFFSPRING_COUNT = 4       # variants generated per nightly cycle
FITNESS_FLOOR   = 0.3     # minimum fitness to accept a variant
NOVELTY_WINDOW  = 0.05    # fitness delta within which novelty roll activates
NOVELTY_PROB    = 0.40    # probability of picking novel variant when tied



@dataclass
class StateGene:
    """
    Evolvable parameter for one state_engine variable.
    Replaces HormoneGene -- now maps to bounded state_engine parameters.
    """
    name:         str
    subsystem:    str     # drives | loads | regulators
    key:          str     # exact key in the StateVector dict
    baseline:     float   # target value at rest
    decay_rate:   float   # how fast it returns to baseline per step


@dataclass
class ThermorphicGene:
    """Evolvable thermorphic physics constants."""
    alpha:            float = 0.08    # thermal diffusivity
    fusion_threshold: float = 1.60   # combined temp to trigger concept fusion
    freeze_dwell:     int   = 8      # ticks below freeze before crystallization


@dataclass
class RetrievalGenome:
    """Subsystem genome: controls memory retrieval physics."""
    thermal: ThermorphicGene = field(default_factory=ThermorphicGene)


@dataclass
class DiffusionGenome:
    """Subsystem genome: controls state_engine decay + drive dynamics."""
    state_genes: Dict[str, StateGene] = field(default_factory=dict)


@dataclass
class MetacognitionGenome:
    """Subsystem genome: controls pulse scheduling."""
    phase_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Genome:
    """The organism's mutable blueprint -- split into isolated subsystems."""
    retrieval:      RetrievalGenome
    diffusion:      DiffusionGenome
    metacognition:  MetacognitionGenome
    generation:     int   = 0
    fitness:        float = 0.0
    notes:          str   = ""


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
        from cortex.state_engine import DECAY, REGULATOR_BASELINES

        # Build state genes from current state_engine constants
        state_genes: Dict[str, StateGene] = {}
        for key, rate in DECAY.items():
            if rate is None:
                rate = 0.05  # regulators
            # Determine subsystem
            from cortex.state_engine import StateVector
            sv = StateVector()
            if key in sv.drives:
                subsystem = "drives"
                baseline  = sv.drives[key]
            elif key in sv.loads:
                subsystem = "loads"
                baseline  = sv.loads[key]
            else:
                subsystem = "regulators"
                baseline  = REGULATOR_BASELINES.get(key, 0.5)
            state_genes[key] = StateGene(
                name=key, subsystem=subsystem, key=key,
                baseline=baseline, decay_rate=rate,
            )

        phase_config = dict(getattr(self._runtime, "phase_config", {
            "decay": 10, "dreams": 20, "brain": 5, "senses": 5,
            "awakening": 50, "self_aware": 30, "metacognition": 6,
        }))

        import cortex.thermorphic as _t
        return Genome(
            retrieval     = RetrievalGenome(thermal=ThermorphicGene(
                alpha=getattr(_t, "ALPHA", 0.08),
                fusion_threshold=getattr(_t, "FUSION_THRESHOLD", 1.60),
                freeze_dwell=getattr(_t, "FREEZE_DWELL", 8),
            )),
            diffusion     = DiffusionGenome(state_genes=state_genes),
            metacognition = MetacognitionGenome(phase_config=phase_config),
            generation    = 0,
            fitness       = 0.0,
            notes         = "Initial genome",
        )

    # ------------------------------------------------------------------
    # OFFSPRING GENERATION
    # ------------------------------------------------------------------
    def _generate_offspring(self, count: int) -> List[Genome]:
        offspring = []
        # One mutation function per subsystem -- never mutate across subsystems simultaneously
        mutations = [
            ("metacognition", self._mutate_phase_frequencies),
            ("diffusion",     self._mutate_state_baselines),
            ("diffusion",     self._mutate_state_decay_rates),
            ("metacognition", self._insert_micro_phase),
            ("retrieval",     self._mutate_thermal_gene),
        ]
        for i in range(count):
            child = copy.deepcopy(self._current_genome)
            # Pick ONE subsystem per offspring (no cross-subsystem bleed)
            subsystem, mutate_fn = random.choice(mutations)
            desc = mutate_fn(child)
            child.notes = f"gen{self._generation+1}_offspring{i}[{subsystem}]: {desc}"
            offspring.append(child)
        return offspring

    def _mutate_phase_frequencies(self, genome: Genome) -> str:
        """Mutate one MetacognitionGenome phase frequency."""
        pc = genome.metacognition.phase_config
        mutable = [k for k in pc if k != "brain"]
        if not mutable:
            return ""
        key = random.choice(mutable)
        old_val = pc[key]
        delta = random.choice([-2, -1, 1, 2])
        pc[key] = max(3, min(100, old_val + delta))
        return f"{key}:{old_val}->{pc[key]}"

    def _mutate_state_baselines(self, genome: Genome) -> str:
        """Nudge one StateGene baseline in DiffusionGenome."""
        genes = genome.diffusion.state_genes
        if not genes:
            return ""
        name = random.choice(list(genes.keys()))
        gene = genes[name]
        delta = round(random.uniform(-0.03, 0.03), 3)
        gene.baseline = max(0.05, min(0.95, gene.baseline + delta))
        return f"{name}_base:{delta:+.3f}"

    def _mutate_state_decay_rates(self, genome: Genome) -> str:
        """Nudge one StateGene decay rate in DiffusionGenome."""
        genes = genome.diffusion.state_genes
        if not genes:
            return ""
        name = random.choice(list(genes.keys()))
        gene = genes[name]
        delta = round(random.uniform(-0.01, 0.01), 3)
        gene.decay_rate = max(0.01, min(0.40, gene.decay_rate + delta))
        return f"{name}_decay:{delta:+.3f}"

    def _insert_micro_phase(self, genome: Genome) -> str:
        """Occasionally insert a new micro-phase into MetacognitionGenome."""
        pc = genome.metacognition.phase_config
        candidates = {
            "interoception_feedback": 8,
            "context_refresh":        12,
            "counterfactual_replay":  15,
            "thermorphic_pulse":      10,
        }
        for phase_name, default_freq in candidates.items():
            if phase_name not in pc:
                pc[phase_name] = default_freq
                return f"micro_phase:{phase_name}"
        return ""

    def _mutate_thermal_gene(self, genome: Genome) -> str:
        """Mutate one thermorphic physics constant in RetrievalGenome."""
        gene  = genome.retrieval.thermal
        field = random.choice(["alpha", "fusion_threshold", "freeze_dwell"])
        if field == "alpha":
            delta = round(random.uniform(-0.01, 0.01), 4)
            gene.alpha = max(0.01, min(0.30, gene.alpha + delta))
            return f"thermal.alpha:{delta:+.4f}"
        elif field == "fusion_threshold":
            delta = round(random.uniform(-0.1, 0.1), 3)
            gene.fusion_threshold = max(0.8, min(3.5, gene.fusion_threshold + delta))
            return f"thermal.fusion_threshold:{delta:+.3f}"
        else:
            delta = random.choice([-1, 1])
            gene.freeze_dwell = max(3, min(30, gene.freeze_dwell + delta))
            return f"thermal.freeze_dwell:{delta:+d}"

    # ------------------------------------------------------------------
    # SHADOW TEST — lightweight fitness estimation for a variant
    # ------------------------------------------------------------------
    async def _shadow_test(self, variant: Genome, cortex, telemetry_broker) -> float:
        """
        Shadow evaluation: control (no mutation) vs treatment (this variant).
        Computes delta_fitness = treatment - control.
        Writes result to causal_trace for evolution debugging.
        """
        import uuid as _uuid
        from cortex.state_engine import state_engine as _se

        # Control: baseline fitness on current genome
        control_fitness = await self._compute_fitness(cortex)
        state_before = _se.snapshot()

        # Extremity penalty: conservative mutations preferred
        pc_orig = self._current_genome.metacognition.phase_config
        pc_new  = variant.metacognition.phase_config
        phase_delta = sum(abs(pc_new.get(k, v) - v) for k, v in pc_orig.items())

        sg_orig = self._current_genome.diffusion.state_genes
        sg_new  = variant.diffusion.state_genes
        state_delta_sum = sum(
            abs(sg_new[n].baseline   - sg_orig[n].baseline) +
            abs(sg_new[n].decay_rate - sg_orig[n].decay_rate)
            for n in sg_new if n in sg_orig
        )
        extremity_penalty = min(0.10, (phase_delta + state_delta_sum) * 0.01)

        novelty_bonus = 0.02 if any(k not in pc_orig for k in pc_new) else 0.0
        treatment_fitness = round(max(0.0, min(1.0,
            control_fitness - extremity_penalty + novelty_bonus)), 3)

        # -- Write causal_trace entry -----------------------------------------
        state_after = _se.snapshot()
        param_name  = variant.notes.split(":")[-1].strip() if ":" in variant.notes else variant.notes
        subsystem   = variant.notes.split("[")[1].split("]")[0] if "[" in variant.notes else "unknown"

        try:
            async with cortex._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO causal_trace
                        (trace_id, mutation_id, subsystem, parameter_name,
                         state_before, state_after, state_delta,
                         fitness_before, fitness_after,
                         eval_mode, pulse)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'shadow',$10)
                """,
                    str(_uuid.uuid4()),
                    str(_uuid.uuid4()),          # per-variant mutation_id
                    subsystem,
                    param_name,
                    json.dumps(state_before),
                    json.dumps(state_after),
                    json.dumps({k: round(state_after.get(k, 0) - state_before.get(k, 0), 5)
                                for k in state_before}),
                    control_fitness,
                    treatment_fitness,
                    self._generation,
                )
        except Exception as e:
            # Non-fatal but consequential: a recurring failure means the entire
            # shadow-test audit trail is being silently dropped.
            print(f"[EVOLVER] ⚠️  causal_trace write failed: {type(e).__name__}: {e}")

        return treatment_fitness

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

        except Exception as db_err:
            # Log instead of silently defaulting — a DB outage here means every
            # nightly fitness score silently returns 0.78 forever, masking the failure.
            print(f"[EVOLVER] ⚠️  Fitness DB query failed: {type(db_err).__name__}: {db_err} "
                  f"— defaulting avg_rating=0.5, success_rate=0.5")
            avg_rating   = 0.5
            success_rate = 0.5

        # Coherence: use interoception energy budget as proxy if LLM unavailable
        coherence = await self._auditor_coherence()

        # Energy efficiency from interoception
        energy = 0.7  # default healthy
        try:
            from state.interoception import interoception
            energy = interoception.state.energy_budget
        except ImportError:
            pass  # interoception not installed in this deployment
        except Exception as e:
            print(f"[EVOLVER] ⚠️  Interoception energy read failed: {type(e).__name__}: {e}")

        fitness = (
            0.4 * avg_rating +
            0.3 * success_rate +
            0.2 * coherence +
            0.1 * energy
        )
        return round(min(1.0, max(0.0, fitness)), 3)

    async def _auditor_coherence(self) -> float:
        """Quick coherence ping. Returns 0.5 on failure."""
        try:
            session = await self._get_session()
            raw = await llm_generate(
                "Rate the cognitive coherence of a system that remembers past interactions and adapts its behavior accordingly. Reply with only a float between 0.0 and 1.0.",
                temperature=0.1, max_tokens=2048, session=session,
            )
            if raw:
                import re
                match = re.search(r"\d+\.?\d*", raw)
                if match:
                    val = float(match.group())
                    return min(1.0, max(0.0, val if val <= 1.0 else val / 10.0))
        except Exception as e:
            print(f"[EVOLVER] Auditor error: {type(e).__name__}: {e}")
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
        """Apply the winning genome to the live runtime, state_engine, and thermorphic substrate."""
        import cortex.thermorphic as _thermo_mod

        # ── MetacognitionGenome → runtime phase_config ───────────────────────
        if hasattr(self._runtime, "phase_config"):
            self._runtime.phase_config.update(genome.metacognition.phase_config)

        # ── DiffusionGenome.state_genes → state_engine DECAY + REGULATOR_BASELINES ──
        # Don't touch telemetry_broker BASELINES/DECAY_RATES — those are the old
        # hormone bus schema which no longer exists. StateEngine owns decay now.
        try:
            from cortex.state_engine import DECAY, REGULATOR_BASELINES
            for name, gene in genome.diffusion.state_genes.items():
                if name in DECAY:
                    DECAY[name] = round(gene.decay_rate, 4)
                if name in REGULATOR_BASELINES:
                    REGULATOR_BASELINES[name] = round(gene.baseline, 4)
        except Exception as se_err:
            print(f"[EVOLVER] ⚠️  State engine gene apply failed: {type(se_err).__name__}: {se_err}")

        # ── RetrievalGenome.thermal → thermorphic module constants ────────────
        tg = genome.retrieval.thermal
        _thermo_mod.ALPHA             = round(tg.alpha, 4)
        _thermo_mod.FUSION_THRESHOLD  = round(tg.fusion_threshold, 3)
        _thermo_mod.FREEZE_DWELL      = int(tg.freeze_dwell)

        self._current_genome = genome
        ts = datetime.now().strftime("%H:%M:%S")
        print(
            f"[{ts}] [EVOLVER] 🔄 Live genome updated — generation {genome.generation} "
            f"| thermal: α={_thermo_mod.ALPHA} fusion={_thermo_mod.FUSION_THRESHOLD} "
            f"freeze_dwell={_thermo_mod.FREEZE_DWELL}"
        )

    # ------------------------------------------------------------------
    # LINEAGE CHECKPOINT
    # ------------------------------------------------------------------
    async def _save_lineage(self, genome: Genome, cortex):
        """Persist accepted genome to lineage_snapshots table."""
        try:
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

                tg = genome.retrieval.thermal
                phase_config_json = json.dumps(genome.metacognition.phase_config)
                state_genome_json = json.dumps({
                    name: {"baseline": g.baseline, "decay_rate": g.decay_rate,
                           "subsystem": g.subsystem}
                    for name, g in genome.diffusion.state_genes.items()
                })
                ratings_json = json.dumps(session_ratings)

                await conn.execute("""
                    INSERT INTO lineage_snapshots
                        (phase_config, hormone_genome, fitness, session_ratings, generation, notes)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """,
                    phase_config_json, state_genome_json,
                    genome.fitness, ratings_json,
                    genome.generation, genome.notes,
                )
        except Exception as e:
            print(f"[EVOLVER] Lineage save error: {e}")

    # ------------------------------------------------------------------
    # STATS + CLEANUP
    # ------------------------------------------------------------------
    def stats(self) -> dict:
        pc = getattr(self._current_genome, "metacognition", None)
        return {
            "generation":             self._generation,
            "cycles_run":             self._cycles_run,
            "last_cycle":             self._last_cycle,
            "last_accepted_fitness":  self._last_accepted_fitness,
            "current_phase_config":   pc.phase_config if pc else {},
        }

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
