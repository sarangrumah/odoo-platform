"""Embedding endpoint — routes to provider that supports embeddings."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..providers import get_provider

router = APIRouter(prefix="/v1", tags=["embed"])


class EmbedIn(BaseModel):
    text: str | list[str]
    model: str | None = None
    provider_override: str | None = Field(
        default=None, description="anthropic does not support embeddings; defaults to openai if anthropic is configured"
    )


class EmbedOut(BaseModel):
    vectors: list[list[float]]
    dim: int
    provider: str
    model: str | None


@router.post("/embed", response_model=EmbedOut)
async def embed(body: EmbedIn) -> EmbedOut:
    name = body.provider_override
    if name is None:
        # If default provider is anthropic, fall back to openai for embeddings
        from ..config import get_settings

        settings = get_settings()
        name = "openai" if settings.ai_provider == "anthropic" else settings.ai_provider

    try:
        provider = get_provider(name)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)) from e

    try:
        vectors = await provider.embed(body.text, body.model)
    except NotImplementedError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    dim = len(vectors[0]) if vectors and vectors[0] else 0
    return EmbedOut(vectors=vectors, dim=dim, provider=provider.name, model=body.model)
