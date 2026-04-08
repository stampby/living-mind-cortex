import sys
import os

# Create mock sovereign-agents/sovereign/registry.py
os.makedirs("/tmp/mock_agents/sovereign", exist_ok=True)
with open("/tmp/mock_agents/sovereign/__init__.py", "w") as f: f.write("")
with open("/tmp/mock_agents/sovereign/registry.py", "w") as f: f.write("class AgentRegistry: pass\n")

# Add to sys.path
sys.path.insert(0, "/tmp/mock_agents")

# Add extend_path to the local sovereign/__init__.py
with open("/home/frost/Desktop/living-mind-cortex/sovereign/__init__.py", "r") as f:
    text = f.read()
if "pkgutil" not in text:
    with open("/home/frost/Desktop/living-mind-cortex/sovereign/__init__.py", "w") as f:
        f.write("from pkgutil import extend_path\n__path__ = extend_path(__path__, __name__)\n" + text)

from sovereign.registry import AgentRegistry
print("SUCCESS!")
