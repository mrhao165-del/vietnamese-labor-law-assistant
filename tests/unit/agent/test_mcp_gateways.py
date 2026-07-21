from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, cast

import pytest

from vietnamese_labor_law_assistant.agent.mcp_gateways import RetrievalMcpGateway


class _Response:
    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return {"ok": True}


class _RetrievalClient:
    def __init__(self) -> None:
        self.article_number: int | None = None

    @asynccontextmanager
    async def session(self):
        yield object()

    async def get_article(self, session: object, article_number: int) -> _Response:
        del session
        self.article_number = article_number
        return _Response()


@pytest.mark.asyncio
async def test_get_article_adapts_router_article_id_to_mcp_article_number() -> None:
    client = _RetrievalClient()

    response = await RetrievalMcpGateway(cast(Any, client)).execute(
        "get_article", {"article_id": 35}
    )

    assert response == {"ok": True}
    assert client.article_number == 35
