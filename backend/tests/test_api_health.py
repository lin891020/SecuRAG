"""Tests for the health check endpoint."""

from unittest.mock import AsyncMock, patch

import pytest


class TestHealthEndpoint:
    async def test_health_returns_200(self, client):
        """Health endpoint should always return 200."""
        with (
            patch("app.api.health._check_postgres", new_callable=AsyncMock, return_value=True),
            patch("app.api.health._check_chromadb", new_callable=AsyncMock, return_value=True),
            patch("app.api.health._check_ollama", new_callable=AsyncMock, return_value=True),
        ):
            resp = await client.get("/api/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "llm_provider" in data
        assert "guardrails_enabled" in data

    async def test_health_degraded_when_service_down(self, client):
        """Status should be 'degraded' if any dependency is down."""
        with (
            patch("app.api.health._check_postgres", new_callable=AsyncMock, return_value=True),
            patch("app.api.health._check_chromadb", new_callable=AsyncMock, return_value=False),
            patch("app.api.health._check_ollama", new_callable=AsyncMock, return_value=True),
        ):
            resp = await client.get("/api/health")

        data = resp.json()
        assert data["status"] == "degraded"
        assert data["services"]["chromadb"] is False
        assert data["services"]["postgres"] is True

    async def test_health_all_services_down(self, client):
        """All services down should still return 200 with degraded status."""
        with (
            patch("app.api.health._check_postgres", new_callable=AsyncMock, return_value=False),
            patch("app.api.health._check_chromadb", new_callable=AsyncMock, return_value=False),
            patch("app.api.health._check_ollama", new_callable=AsyncMock, return_value=False),
        ):
            resp = await client.get("/api/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert all(v is False for v in data["services"].values())
