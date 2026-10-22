"""Run the ADK company verifier as an A2A service."""
import os

import uvicorn
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .agent import root_agent

a2a_app = to_a2a(
    root_agent,
    host=os.getenv("A2A_ADVERTISED_HOST", "127.0.0.1"),
    port=int(os.getenv("A2A_ADVERTISED_PORT", os.getenv("PORT", "8001"))),
    protocol=os.getenv("A2A_PROTOCOL", "http"),
)

if __name__ == "__main__":
    uvicorn.run(a2a_app, host="0.0.0.0", port=int(os.getenv("PORT", "8001")))
