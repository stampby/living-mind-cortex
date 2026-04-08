from cortex.hologram import HolographicSuperposition
from cortex.thermorphic import ConceptNode, encode_atom
import numpy as np

print("Initializing HSM...")
hsm = HolographicSuperposition(dims=256)

concepts = [
    "The database is down due to a missing index.",
    "Agent Zola deployed a sub-agent to fix the pipeline.",
    "The secure password for the alpha server is hunter2.",
    "BGP routes converged at 0400 hours globally.",
    "Holographic memory operates purely in O(D) complexity."
]

nodes = {}
for i, c in enumerate(concepts):
    nodes[f"id_{i}"] = ConceptNode(
        id=f"id_{i}",
        content=c,
        hvec=encode_atom(c, 256),
        temperature=2.0,
        born_at_pulse=0,
    )

hsm.update(nodes)
print(f"HSM magnitude (SNR proxy): {hsm.decode_magnitude():.3f}")

# Unbind
query = "The secure password for the alpha server is hunter2."
q_vec = encode_atom(query, 256)

cand_phase = hsm.unbind(q_vec)
best_node, best_score = hsm.decode_best_match(cand_phase)
print(f"Query: {query}")
if best_node:
    print(f"Best match in hot path: {best_node.content} | Score: {best_score:.3f}")
else:
    print("No matching node.")
