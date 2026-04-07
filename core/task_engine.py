"""
Task Engine — Living Mind
Category: Autonomy/Integration

Persists long-term objectives across multiple pulse loops.
Prevents the runtime from suffering 'goldfish memory' by holding
the current mission and sequence of steps in active state.
"""

from typing import List, Dict
from datetime import datetime

class TaskEngine:
    def __init__(self):
        self.active_mission: str = ""
        self.status: str = "idle"  # idle, active, completed, failed
        self.steps_taken: List[str] = []
        self.started_at: float = 0.0

    def start_mission(self, description: str):
        self.active_mission = description
        self.status = "active"
        self.steps_taken = []
        self.started_at = datetime.now().timestamp()
        print(f"[TASK ENGINE] 🎯 New Mission Started: {self.active_mission}")

    def add_step(self, step_description: str):
        if self.status == "active":
            self.steps_taken.append(step_description)
            print(f"[TASK ENGINE] 👣 Step Logged: {step_description}")

    def complete_mission(self, conclusion: str = ""):
        if self.status == "active":
            self.status = "completed"
            if conclusion:
                self.steps_taken.append(f"Conclusion: {conclusion}")
            print(f"[TASK ENGINE] ✅ Mission Completed: {self.active_mission}")

    def fail_mission(self, reason: str = ""):
        if self.status == "active":
            self.status = "failed"
            if reason:
                self.steps_taken.append(f"Failure Reason: {reason}")
            print(f"[TASK ENGINE] ❌ Mission Failed: {self.active_mission} | {reason}")

    def get_context_block(self) -> str:
        if self.status != "active":
            return "[ACTIVE MISSION]: None"
        
        steps_str = "\n".join(f"  - {s}" for s in self.steps_taken[-5:])
        if not steps_str:
            steps_str = "  (No steps taken yet)"
            
        return f"[ACTIVE MISSION]: {self.active_mission}\n[RECENT STEPS]:\n{steps_str}"

    def report(self) -> dict:
        return {
            "active_mission": self.active_mission,
            "status": self.status,
            "steps_count": len(self.steps_taken),
        }

# Singleton
task_engine = TaskEngine()
