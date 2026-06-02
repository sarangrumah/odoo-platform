"""Personal shopper: retrieval-controlled assistant grounded on the Odoo catalog.

The shopper does NOT use LLM tool-calling. Instead the flow is deterministic:

    1. extract intent from the conversation (one JSON-mode LLM call)
    2. query the live Odoo catalog API *in code* using that intent
    3. synthesise a natural-language reply from the real results (one LLM call)

This keeps grounding strong and latency low (<=2 inferences/turn) on small local
models served by Ollama, where multi-round agentic tool-calling is unreliable.
"""
