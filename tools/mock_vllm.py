import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict

app = FastAPI(title="Mock vLLM Endpoint")

class ChatRequest(BaseModel):
    model: str
    messages: List[Dict[str, str]]
    max_tokens: int = 2048
    temperature: float = 0.2

class LoadLoraRequest(BaseModel):
    lora_name: str
    lora_path: str

class UnloadLoraRequest(BaseModel):
    lora_name: str

# Track loaded adapters in-process for the mock
loaded_adapters: set[str] = set()

@app.get("/v1/models")
async def mock_models():
    # Base model is always there
    data = [{"id": "meta-llama/Meta-Llama-3-8B-Instruct", "object": "model"}]
    # Add loaded LoRAs
    for lora in loaded_adapters:
        data.append({"id": lora, "object": "model"})
    return {"object": "list", "data": data}

@app.post("/v1/load_lora_adapter")
async def mock_load_lora(request: LoadLoraRequest):
    print(f"[Mock vLLM] Loading adapter: {request.lora_name} from {request.lora_path}")
    loaded_adapters.add(request.lora_name)
    return {"status": "ok"}

@app.post("/v1/unload_lora_adapter")
async def mock_unload_lora(request: UnloadLoraRequest):
    print(f"[Mock vLLM] Unloading adapter: {request.lora_name}")
    loaded_adapters.discard(request.lora_name)
    return {"status": "ok"}

@app.post("/v1/chat/completions")
async def mock_completions(request: ChatRequest):
    # Verify the requested model is actually loaded (if it's not the base model)
    is_base = request.model == "meta-llama/Meta-Llama-3-8B-Instruct"
    if not is_base and request.model not in loaded_adapters:
        print(f"[Mock vLLM] ERROR: Requested adapter '{request.model}' is NOT loaded!")
        return {"error": {"message": f"Model '{request.model}' is not loaded.", "type": "invalid_request_error"}}

    print(f"[Mock vLLM] Connection established. Requested adapter: {request.model}")
    
    # Extract the prompt to prove payload integrity
    prompt = request.messages[0]["content"] if request.messages else ""
    
    # Generate the simulated response
    simulated_output = f"Simulated inference executed successfully using hemisphere: {request.model}. Prompt excerpt: '{prompt[:40]}...'"
    
    return {
        "id": "mock-cmpl-123",
        "object": "chat.completion",
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": simulated_output
                },
                "finish_reason": "stop"
            }
        ]
    }

if __name__ == "__main__":
    print("Starting Mock vLLM Server on http://localhost:8001...")
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
