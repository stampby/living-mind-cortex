import asyncio
import numpy as np
from cortex.thermorphic import substrate as _thermal_substrate, encode_atom

async def test():
    print("Initializing Cortex and HSM...")

    # Inject 5 nodes into the thermal substrate
    concepts = [
        "The database is down due to a missing index.",
        "Agent Zola deployed a sub-agent to fix the pipeline.",
        "The secure password for the alpha server is hunter2.",
        "BGP routes converged at 0400 hours globally.",
        "Holographic memory operates purely in O(D) complexity."
    ]

    for c in concepts:
        _thermal_substrate.inject(c, temperature=1.5, dims=256)

    _thermal_substrate.pulse()
    print(f"HSM magnitude:  {_thermal_substrate.hsm.decode_magnitude():.4f}")
    print(f"Hot nodes:      {len(_thermal_substrate.hsm.active_hot_nodes)}")
    print()

    queries = [
        "What is the password for alpha server?",
        "Is the database online?",
        "Tell me about holographic memory complexity.",
        "Did any BGP changes happen overnight?",
    ]

    for query in queries:
        q_vec = encode_atom(query, dim=256)

        # ── Direct Auto-Associative Scoring (no unbind) ────────────────────────
        scores = []
        for node in _thermal_substrate.hsm.active_hot_nodes.values():
            sim = float(np.mean(np.cos(q_vec - node.hvec)))
            scores.append((sim, node))
        scores.sort(key=lambda x: x[0], reverse=True)

        best_sim, best_node = scores[0] if scores else (0.0, None)
        content = best_node.content if best_node else "None"
        hit = "✅ HSM HIT " if best_sim > 0.30 else "↩️  fallback"
        print(f"Query: '{query}'")
        print(f"  {hit}  Score: {best_sim:.3f}  → {content[:70]}")
        print()

if __name__ == "__main__":
    asyncio.run(test())
