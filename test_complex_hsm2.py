import numpy as np
TWO_PI = 2 * np.pi
np.random.seed(42)
dim = 256
mem1 = np.random.uniform(0, TWO_PI, dim)
mem2 = np.random.uniform(0, TWO_PI, dim)
mem3 = np.random.uniform(0, TWO_PI, dim)

def to_complex(p): return np.exp(1j * p)
def to_phase(c): return np.mod(np.angle(c), TWO_PI)

H_comp = to_complex(mem1) + to_complex(mem2) + to_complex(mem3)
H_phase = to_phase(H_comp)

def sim(a, b): return float(np.mean(np.cos(a - b)))

print("Sim H to mem1:", sim(H_phase, mem1))
print("Sim H to rand:", sim(H_phase, np.random.uniform(0, TWO_PI, dim)))
