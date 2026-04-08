"""
Boundary Condition Evaluation (Thermal Collisions)
===================================================
Automatically searches for the minimum pulse gap required to achieve 
a clean thermal resolution between two conflicting state anomalies.

If a state mutation arrives faster than this gap, the Substrate should 
throw a Thermal Collision warning and defer to an LLM for manual resolution,
or force a sleep cycle.

Usage:
    python3 benchmarks/boundary_condition_eval.py
"""

import sys
sys.path.insert(0, ".")
from cortex.thermorphic import ThermorphicSubstrate

def run_boundary_sweep():
    print(f"\n{'='*70}")
    print("  BOUNDARY CONDITION SWEEP (Thermal Collision Constants)")
    print(f"{'='*70}\n")
    
    print("[*] Sweeping pulse delay to find safe context resolution boundary...")
    print("[*] Target Margin: Delta_T > 0.5\n")
    
    safe_gap = -1
    
    for pulses in range(1, 15):
        db = ThermorphicSubstrate()
        db.inject("The database port is 5432.", temperature=1.8, dims=64)
        
        # Simulate time passing
        for _ in range(pulses):
            db.pulse()
            
        old_temp = list(db.nodes.values())[0].temperature
        
        # Inject the state mutation
        db.inject("The database port is 8080.", temperature=1.8, dims=64)
        
        # Run 1 pulse for initial diffusion equilibrium of the new node
        db.pulse()
        
        new_temp = list(db.nodes.values())[1].temperature
        
        diff = new_temp - old_temp
        is_clean = diff > 0.5
        
        status = "✅ CLEAN" if is_clean else "❌ COLLISION"
        print(f"  Gap: {pulses:2d} pulses | Old_T: {old_temp:.3f} | New_T: {new_temp:.3f} | Margin: {diff:.3f} | {status}")
        
        if is_clean and safe_gap == -1:
            safe_gap = pulses
            break

    print(f"\n{'='*70}")
    print(f"  SYSTEM CONSTANT DISCOVERED")
    print(f"{'='*70}")
    print(f"  SAFE_MUTATION_GAP = {safe_gap} pulses")
    print(f"")
    print(f"  Implementation Guideline:")
    print(f"  If a direct contradiction is detected with a $\\Delta T < 0.5$,")
    print(f"  the system is in a Thermal Collision. Default action:")
    print(f"  `if delta_t < 0.5: await llm.resolve_collision(node_a, node_b)`")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    run_boundary_sweep()
