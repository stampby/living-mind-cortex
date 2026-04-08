import numpy as np
import logging
from typing import Dict, Any, Tuple

_TWO_PI = 2.0 * np.pi

logger = logging.getLogger("SovereignHologram")

class HolographicSuperposition:
    def __init__(self, dims=256, dim=None):
        self.dims = dim if dim is not None else dims
        self.complex_holo = np.zeros(self.dims, dtype=complex)
        self.active_hot_nodes: Dict[str, Any] = {}
        
    def decode_magnitude(self) -> float:
        return float(np.mean(np.abs(self.complex_holo)))
        
    def superpose(self, hvecs: list[np.ndarray]):
        """Superpose a list of phase vectors by projecting to complex plane."""
        for phi in hvecs:
            c = np.exp(1j * phi)
            self.complex_holo += c
            
    def unbind(self, query_hvec: np.ndarray) -> np.ndarray:
        """
        Unbinds a query phase vector from the complex superposition.
        Equivalent to Hologram * Conj(Query).
        """
        probe = np.exp(1j * query_hvec)
        decoded_complex = self.complex_holo * np.conj(probe)
        decoded_phase = np.angle(decoded_complex) % _TWO_PI
        return decoded_phase
        
    def update(self, hot_nodes: Dict[str, Any]):
        """
        Refresh the hologram using the currently active nodes from the thermal cycle.
        """
        self.active_hot_nodes = hot_nodes
        self.complex_holo = np.zeros(self.dims, dtype=complex)
        
        active_hvecs = [n.hvec for n in hot_nodes.values() if n.hvec is not None]
        if active_hvecs:
            self.superpose(active_hvecs)

    def decode_best_match(self, candidate_phase: np.ndarray) -> Tuple[Any, float]:
        """
        Cleanup step: compare the algebraically unbound phase against active nodes.
        Note for Auto-Association: To check if Q is in H natively, we compare Angle(H) with Q directly.
        If candidate_phase already is (H - Q), then node matching depends on the associative topology.
        """
        best_node = None
        best_score = -2.0

        for node in self.active_hot_nodes.values():
            # Standard HRR cosine phase similarity
            score = float(np.mean(np.cos(candidate_phase - node.hvec)))
            if score > best_score:
                best_score = score
                best_node = node
                
        return best_node, best_score

if __name__ == "__main__":
    # VERIFICATION BLOCK
    # Testing SNR degradation against N_hot
    dim = 256
    
    print(f"--- HSM SNR DEGRADATION TEST (D={dim}) ---")
    print(f"Theoretical Cliff: ~{int(0.5 * np.sqrt(dim))} items\\n")
    
    for n_memories in [5, 10, 16, 25, 50, 100]:
        hsm = HolographicSuperposition(dim=dim)
        
        # Following the snippet structure provided, but matching the new complex methods.
        # Generating Key-Value bindings for pure algebraic evaluation
        keys = np.random.uniform(0, 2*np.pi, (n_memories, dim))
        values = np.random.uniform(0, 2*np.pi, (n_memories, dim))
        
        # Traces: K * V (phase addition)
        traces = [(k + v) % _TWO_PI for k, v in zip(keys, values)]
        
        # Superpose into one complex hologram
        hsm.superpose(traces)
        
        # Query for the first item
        target_idx = 0
        query_key = keys[target_idx]
        actual_target = values[target_idx]
        
        # Unbind -> surfaces Noisy V
        recovered_noisy_target = hsm.unbind(query_key)
        
        # Measure Signal vs Noise
        target_sim = np.mean(np.cos(recovered_noisy_target - actual_target))
        
        noise_sims = [np.mean(np.cos(recovered_noisy_target - values[i])) for i in range(1, n_memories)]
        avg_noise = np.mean(noise_sims) if noise_sims else 0.0
        
        print(f"N={n_memories:<3} | Target Sim: {target_sim:.3f} | Noise Floor: {avg_noise:.3f} | Margin: {target_sim - avg_noise:.3f}")
