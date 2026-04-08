import numpy as np

TWO_PI = 2 * np.pi
np.random.seed(42)

dim = 256
mem1 = np.random.uniform(0, TWO_PI, dim)
mem2 = np.random.uniform(0, TWO_PI, dim)
mem3 = np.random.uniform(0, TWO_PI, dim)

hologram = (mem1 + mem2 + mem3) % TWO_PI

# Unbind to find partner of mem1: query = mem1
# But wait, query is a word. You want to retrieve mem1 itself if you prompt with mem1?
# No, if hologram has mem1, and we unbind mem1, we get the rest of the superposition!
# But what if we want to query: "what is in the hologram similar to query?"
# The user says:
# query_time: candidate = bind(hologram, inverse(query_vec))
# If query_vec ≈ mem1... then candidate = hologram - mem1 = mem2 + mem3. Is candidate similar to mem1? No.

# Wait, the HRR association relies on mem_i = bind(A, B).
# If mem_i is a bound pair, and we query with A, we get B.
# What if we just want to know if query_vec is IN the superposition?
# We would check dot_product(hologram, query_vec). But hologram is a sum mod 2pi. Does phase sum preserve cosine similarity?
sim1 = np.mean(np.cos(hologram - mem1))
print("Sim mem1 in hologram:", sim1)

# Let's see if true HRR superposition works with phase addition modulo 2pi.
# Because phase wrapping is highly non-linear. (a+b) mod 2pi is NOT linearly correlative with a.
# In Plate's HRR, superposition is literally vector addition in Reals, then normalized.
# Let's test it:
a = 0.1
b = 0.2
h = (a + b) % TWO_PI
print(np.cos(h - a) == np.cos(b)) # Yes, cos(h - a) is cos(b), not near 1.0! 

