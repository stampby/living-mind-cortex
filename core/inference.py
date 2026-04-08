import httpx
import json
from pathlib import Path

class SovereignInferenceClient:
    """
    Executes the generation pass, respecting the BiomechanicRouter's LoRA state.
    Assumes vLLM is running locally with --enable-lora.

    Also manages the physical VRAM adapter lifecycle:
      load_lora()   → POST /v1/load_lora_adapter   (called on first resonance)
      unload_lora() → POST /v1/unload_lora_adapter  (called before plasma purge)
    """
    def __init__(self, vllm_url="http://localhost:8001/v1"):
        self.vllm_url = vllm_url
        self.base_model_name = "meta-llama/Meta-Llama-3-8B-Instruct" # The persistent substrate
        # Track which adapters are physically resident in VRAM.
        # Prevents redundant load calls on hot-path routing.
        self._loaded_adapters: set[str] = set()

    # ── Adapter Lifecycle ───────────────────────────────────────────────

    async def load_lora(self, adapter_id: str, adapter_path: str) -> bool:
        """
        Loads a LoRA adapter into vLLM VRAM via POST /v1/load_lora_adapter.
        No-op if the adapter is already resident (tracked in _loaded_adapters).

        Returns True on success, False on failure (caller should fall back to base_model).
        """
        if adapter_id in self._loaded_adapters:
            return True  # Already hot — skip redundant load

        print(f"[Inference] Loading adapter '{adapter_id}' from {adapter_path}...")
        payload = {"lora_name": adapter_id, "lora_path": str(Path(adapter_path).resolve())}

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                r = await client.post(f"{self.vllm_url}/load_lora_adapter", json=payload)
                r.raise_for_status()
                self._loaded_adapters.add(adapter_id)
                print(f"[Inference] '{adapter_id}' mounted in VRAM.")
                return True
            except httpx.HTTPError as e:
                print(f"[Inference Error] Failed to load '{adapter_id}': {e}")
                return False

    async def unload_lora(self, adapter_id: str) -> bool:
        """
        Evicts a LoRA adapter from VRAM via POST /v1/unload_lora_adapter.
        Must be called BEFORE purging the plasma thermal record.
        If unload fails, the plasma record is NOT purged — we keep tracking it.

        Returns True on success, False on failure.
        """
        if adapter_id not in self._loaded_adapters:
            return True  # Not loaded — nothing to unload

        print(f"[Inference] Evicting adapter '{adapter_id}' from VRAM...")
        payload = {"lora_name": adapter_id}

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                r = await client.post(f"{self.vllm_url}/unload_lora_adapter", json=payload)
                r.raise_for_status()
                self._loaded_adapters.discard(adapter_id)
                print(f"[Inference] '{adapter_id}' evicted from VRAM.")
                return True
            except httpx.HTTPError as e:
                print(f"[Inference Error] Failed to evict '{adapter_id}': {e}. Plasma record preserved.")
                return False

    def is_loaded(self, adapter_id: str) -> bool:
        """Returns True if the adapter is currently resident in VRAM."""
        return adapter_id in self._loaded_adapters

    async def sync_loaded_adapters(self) -> bool:
        """
        Queries the vLLM server (GET /v1/models) to synchronize the local 
        _loaded_adapters set with the actual VRAM state.
        
        This prevents VRAM leaks when the Cortex process restarts but vLLM 
        stays alive with adapters still resident.
        """
        print("[Inference] Synchronizing resident adapters with vLLM...")
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                r = await client.get(f"{self.vllm_url}/models")
                r.raise_for_status()
                data = r.json()
                
                # models list contains both base model and LoRA adapters
                current_models = [m["id"] for m in data.get("data", [])]
                
                # Filter out the base model to find LoRAs
                found_loras = [
                    m for m in current_models 
                    if m != self.base_model_name and m != "base_model"
                ]
                
                # Update local tracking
                self._loaded_adapters = set(found_loras)
                if found_loras:
                    print(f"[Inference] Sync complete. Found {len(found_loras)} "
                          f"resident adapter(s): {found_loras}")
                else:
                    print("[Inference] Sync complete. No resident LoRA adapters found.")
                return True
            except httpx.HTTPError as e:
                print(f"[Inference Error] Failed to sync adapters: {e}")
                return False

    # ── Generation ─────────────────────────────────────────────────────

    async def generate(self, prompt: str, adapter_id: str) -> str:
        """
        Pipes the prompt through the appropriate hemisphere.
        """
        # Target the base weights, or target the specific LoRA adapter name
        target_model = self.base_model_name if adapter_id == "base_model" else adapter_id
        
        print(f"[Inference] Executing pass through hemisphere: {target_model}")
        
        payload = {
            "model": target_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
            "temperature": 0.2
        }
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(f"{self.vllm_url}/chat/completions", json=payload)
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
            except httpx.HTTPError as e:
                print(f"[Inference Error] Substrate failure: {e}")
                return ""
