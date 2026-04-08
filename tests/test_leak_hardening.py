import asyncio
import httpx
import pytest
from core.inference import SovereignInferenceClient
from cortex.adapter_lifecycle import AdapterLifecycleManager
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_vram_sync_recovery():
    """Verify that SovereignInferenceClient recovers tracking state from vLLM."""
    client = SovereignInferenceClient(vllm_url="http://localhost:8001/v1")
    
    # Mock the response from GET /v1/models
    # Includes base model + 2 adapters
    mock_models_response = {
        "object": "list",
        "data": [
            {"id": "meta-llama/Meta-Llama-3-8B-Instruct", "object": "model"},
            {"id": "code_expert", "object": "model"},
            {"id": "logic_expert", "object": "model"}
        ]
    }
    
    mock_client = AsyncMock()
    # Create a synchronous mock for the response
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = mock_models_response
    mock_response.status_code = 200
    
    # Patch httpx.AsyncClient to return our mock_client
    import core.inference
    original_client = core.inference.httpx.AsyncClient
    
    # We need to mock the context manager entrance
    mock_client.__aenter__.return_value = mock_client
    core.inference.httpx.AsyncClient = MagicMock(return_value=mock_client)
    
    # When we await client.get, it should return mock_response
    mock_client.get.return_value = mock_response
    
    try:
        success = await client.sync_loaded_adapters()
        
        assert success is True
        assert "code_expert" in client._loaded_adapters
        assert "logic_expert" in client._loaded_adapters
        assert "meta-llama/Meta-Llama-3-8B-Instruct" not in client._loaded_adapters
        assert len(client._loaded_adapters) == 2
        print("PASS: VRAM sync recovery logic verified.")
    finally:
        core.inference.httpx.AsyncClient = original_client

@pytest.mark.asyncio
async def test_runtime_death_cleanup():
    """Verify that AgentRuntime.death() closes all organ sessions."""
    from core.runtime import AgentRuntime
    import core.runtime
    
    rt = AgentRuntime()
    rt.born_at = 0
    rt.event_loops = 1
    
    # Mock all organs
    mock_evolver = AsyncMock()
    rt.evolver = mock_evolver
    
    core.runtime.brain = AsyncMock()
    core.runtime.dreams = AsyncMock()
    core.runtime.awakening = AsyncMock()
    core.runtime.metacognition = AsyncMock()
    core.runtime.topology_mapper = AsyncMock()
    core.runtime.interoception = AsyncMock()
    core.runtime.research_engine = AsyncMock()
    core.runtime.cortex = AsyncMock()
    
    await rt.death()
    
    # Check if close was called on everyone
    mock_evolver.close.assert_called_once()
    core.runtime.brain.close.assert_called_once()
    core.runtime.dreams.close.assert_called_once()
    core.runtime.awakening.close.assert_called_once()
    core.runtime.metacognition.close.assert_called_once()
    core.runtime.topology_mapper.close.assert_called_once()
    core.runtime.interoception.close.assert_called_once()
    core.runtime.research_engine.close.assert_called_once()
    core.runtime.cortex.disconnect.assert_called_once()
    
    print("PASS: Runtime death cleanup sequence verified.")

if __name__ == "__main__":
    asyncio.run(test_vram_sync_recovery())
    asyncio.run(test_runtime_death_cleanup())
