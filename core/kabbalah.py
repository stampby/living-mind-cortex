from enum import Enum

class Pillar(Enum):
    LEFT = "SEVERITY_RESTRICTION"
    RIGHT = "MERCY_EXPANSION"
    MIDDLE = "MILDNESS_SYNTHESIS"

class Sephirah(Enum):
    KETER = "CROWN_WILL"            # Orchestrator
    CHOCHMAH = "WISDOM_INTUITION"   # Dreams
    BINAH = "UNDERSTANDING_PRUNING" # Cognitive Biases
    CHESED = "KINDNESS_GATEWAY"     # Nodus / Agent Gateway
    GEVURAH = "STRENGTH_JUDGMENT"   # SecurityPerimeter / Security Perimeter
    TIFERET = "BEAUTY_HARMONY"      # Hormone Bus / Telemetry
    NETZACH = "VICTORY_ENDURANCE"   # Autodidact / Research
    HOD = "SUBMISSION_PERCEPTION"   # Senses
    YESOD = "FOUNDATION_CONDUIT"    # Cortex / Memory Engine
    MALKHUT = "KINGDOM_PHYSICAL"    # Motor Cortex / Execution
    
    # The Hidden Knowledge Gateway
    DAAT = "KNOWLEDGE_GATEWAY"      # Seed Axioms Verification 
