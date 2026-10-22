"""Small A2A SDK client used by the CrewAI coordinator to call the ADK service."""
import asyncio
import json
import os
import uuid

import httpx


async def _send_a2a_request(payload: dict) -> dict:
    from a2a.client import A2ACardResolver, ClientConfig, create_client
    from a2a.helpers import get_artifact_text, get_message_text
    from a2a.types import Message, Part, Role, SendMessageRequest

    base_url = os.getenv("A2A_AGENT_URL", "http://127.0.0.1:8001").rstrip("/")
    async with httpx.AsyncClient(timeout=35) as http_client:
        card = await A2ACardResolver(http_client, base_url).get_agent_card()
        config = ClientConfig(supported_protocol_bindings=["JSONRPC"])
        client = await create_client(card, client_config=config)
        message = Message(
            role=Role.ROLE_USER,
            message_id=str(uuid.uuid4()),
            parts=[Part(text=json.dumps(payload, ensure_ascii=False))],
        )

        text_parts: list[str] = []
        try:
            async for event in client.send_message(SendMessageRequest(message=message)):
                if event.HasField("message"):
                    text_parts.append(get_message_text(event.message, delimiter=" "))
                if event.HasField("task"):
                    for artifact in event.task.artifacts:
                        text_parts.append(get_artifact_text(artifact, delimiter=" "))
                    status_message = event.task.status.message
                    if status_message:
                        text_parts.append(get_message_text(status_message, delimiter=" "))
        finally:
            await client.close()

    response_text = "\n".join(part for part in text_parts if part).strip()
    start = response_text.find("{")
    end = response_text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("The ADK verifier returned no JSON result.")
    return json.loads(response_text[start:end + 1])


def verify_company_with_adk(payload: dict) -> dict:
    """Call the separately running ADK verifier using the A2A protocol."""
    return asyncio.run(_send_a2a_request(payload))
