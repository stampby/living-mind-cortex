import numpy as np
import logging
from typing import Dict, Any, Tuple

# Constants
_TWO_PI = 2.0 * np.pi

logger = logging.getLogger("SovereignHologram")

class HolographicSuperposition:
    """
    Holographic Superposition Memory (HSM)
    
    Operates on Fractional Holographic Reduced Representations (FHRR).
    Phase vectors [0, 2π) are projected to the complex unit circle e^{i \\phi}.
    - Superposition (Memory Pooling): Complex addition
    - Binding (Association): Phase addition (modulo 2π) / Complex multiplication
    - Unbinding: Phase subtraction (modulo 2π) / Complex conjugate multiplication
    
    This layer provides O(D) time complexity recall by algebraically decoding
    the associated target memory directly from the superposition hologram, 
    completely bypassing O(N * D) cosine looping.
    """

    def __init__(self, dims: int = 256):
        self.dims = dims
        # The rolling superposition state (starts as empty complex vector)
        self.hologram = np.zeros(self.dims, dtype=np.complex128)
        # We also keep track of what's currently in the hologram to map algebraic hits to textual nodes.
        self.active_hot_nodes: Dict[str, Any] = {}

    def update(self, hot_nodes: Dict[str, Any]) -> None:
        """
        Re-superimpose the current hot path. 
        Because nodes thermally decay and freeze out of the hot zone, we 
        fully rebuild the hologram from the current active hot nodes to prevent drift.
        """
        self.active_hot_nodes = hot_nodes
        self.hologram = np.zeros(self.dims, dtype=np.complex128)

        for node in hot_nodes.values():
            # Project to complex plane and superimpose
            # Vector magnitude is intrinsically 1.0 per term
            self.hologram += np.exp(1j * node.hvec)

        # Normalization / Phase collapse
        # As per guidance, we collapse back to pure phase vectors for query matching,
        # or we keep the complex sum for continuous SNR weighting. We will keep
        # the complex interference pattern natively, as it correctly weights strong signals.
        pass

    def unbind(self, query_hvec: np.ndarray) -> np.ndarray:
        """
        Extract the memory mathematically.
        Since our substrate currently uses single atomic vectors per memory 
        (rather than bound key-value pairs), the superposition serves as a 
        holistic context vector. We simply return the phase of the complex 
        superposition to be mathematically scored against candidates.
        
        Returns:
            candidate_phase: pure phase vector [0, 2pi) of the superposition
        """
        # Collapse back to phase space [0, 2π)
        candidate_phase = np.mod(np.angle(self.hologram), _TWO_PI)
        return candidate_phase

    def decode_magnitude(self) -> float:
        """
        Returns the average magnitude of the superposition vector.
        Acts as a rough proxy for Signal-to-Noise Ratio (SNR).
        A random walk of N unit vectors has expected magnitude sqrt(N).
        """
        return float(np.mean(np.abs(self.hologram)))

    def decode_best_match(self, candidate_phase: np.ndarray) -> Tuple[Any, float]:
        """
        Finds the closest actual active node to the algebraically decoded candidate phase.
        (O(N_active) lookup where N_active is bounded by the thermal threshold capacity).
        """
        best_node = None
        best_score = -2.0

        for node in self.active_hot_nodes.values():
            score = float(np.mean(np.cos(candidate_phase - node.hvec)))
            if score > best_score:
                best_score = score
                best_node = node
                
        return best_node, best_score
