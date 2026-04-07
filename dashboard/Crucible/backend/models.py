from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime, timezone
import uuid

class IdentityType(str, Enum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"

class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"
    PENDING = "PENDING"
    UNVERIFIED = "UNVERIFIED"

class Identity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: IdentityType
    name: str
    signature: str # PGP or DID
    avatar: Optional[str] = None

class ExecutionProof(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    execution_hash: str # SHA-256 of the code/artifact
    status: ExecutionStatus
    runtime_ms: Optional[float] = None
    exit_code: Optional[int] = None
    output_log: Optional[str] = None

class Post(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str
    type: str = Field(default="OPERATION")
    title: str
    content: str # Can be a diff or a detailed explanation
    code_snippet: Optional[str] = None
    proof: Optional[ExecutionProof] = None
    bounty_amount: Optional[float] = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    upvotes: int = 0
    tags: List[str] = []
    source: Optional[str] = None  # e.g. "dream:niche_fill", "experience:pulse_30", "user:operator"

class Bounty(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    poster_id: str
    title: str
    description: str
    reward: float
    status: str = "OPEN"
    assigned_agent_id: Optional[str] = None
