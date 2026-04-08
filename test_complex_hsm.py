import numpy as np
TWO_PI = 2 * np.pi
np.random.seed(42)

dim = 256
mem1 = np.random.uniform(0, TWO_PI, dim)
mem2 = np.random.uniform(0, TWO_PI, dim)
mem3 = np.random.uniform(0, TWO_PI, dim)

# In our framework, binding is a+b mod 2pi.
# Let's say mem1 = bind(topic1, concept1) = (T1 + C1) % 2pi
T1 = np.random.uniform(0, TWO_PI, dim)
C1 = np.random.uniform(0, TWO_PI, dim)
mem1 = (T1 + C1) % TWO_PI

# Create a complex superposition of the memories themselves
def to_complex(phase):
    return np.exp(1j * phase)

def to_phase(comp):
    return np.mod(np.angle(comp), TWO_PI)

# Hologram is sum of complex representations
H_comp = to_complex(mem1) + to_complex(mem2) + to_complex(mem3)

# 1. Decode magnitude to see SNR
print("Hologram complex magnitudes mean:", np.mean(np.abs(H_comp)))

# If we unbind T1 from H_comp: candidate = bind(H, inv(T1))
# Since binding is addition in phase space, and inv is negation in phase space:
# This is equivalent to H_comp * exp(-i * T1)
candidate_comp = H_comp * np.exp(-1j * T1)
candidate_phase = to_phase(candidate_comp)

# We expect candidate_phase to be highly similar to C1!
def cosine_sim(a, b):
    return np.mean(np.cos(a - b))

print("Sim candidate approx C1:", cosine_sim(candidate_phase, C1))
print("Sim candidate approx random:", cosine_sim(candidate_phase, np.random.uniform(0, TWO_PI, dim)))

