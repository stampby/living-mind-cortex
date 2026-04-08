from cortex.hologram import HolographicSuperposition
from cortex.thermorphic import ConceptNode, _random_hvec, _hrr_dot, encode_atom
import numpy as np

print("Initializing HSM...")
hsm = HolographicSuperposition(dims=256)

# Inject 5 hot nodes
nodes = {}
for i, c in enumerate([
    "The database is down due to a missing index.",
    "Agent Zola deployed a sub-agent to fix the pipeline.",
    "The secure password for the alpha server is hunter2.",
    "BGP routes converged at 0400 hours globally.",
    "Holographic memory operates purely in O(D) complexity."
]):
    nodes[f"id_{i}"] = ConceptNode(
        id=f"id_{i}",
        content=c,
        hvec=encode_atom(c, 256),
        temperature=2.0,
        born_at_pulse=0,
    )

print("Updating HSM with hot path...")
hsm.update(nodes)

print(f"HSM magnitude (SNR proxy): {hsm.decode_magnitude():.3f}")

# Unbind
query = "What is the secure password for the alpha server?"
q_vec = encode_atom(query, 256)

cand_phase = hsm.unbind(q_vec)

# Decode best match
best_node, best_score = hsm.decode_best_match(cand_phase)
print(f"Query: {query}")
print(f"Cand vs Target Score: {_hrr_dot(cand_phase, encode_atom('The secure password for the alpha server is hunter2.', 256)):.3f}")
if best_node:
    print(f"Best match in hot path: {best_node.content} | Score: {best_score:.3f}")
else:
    print("No matching node.")

