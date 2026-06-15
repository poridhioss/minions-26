"""Integration tests for the Docker sandboxing service.

⚠ These tests require a running Docker daemon.
They will be automatically skipped if Docker is unavailable.
"""

from __future__ import annotations

import pytest

from app.services.docker_service import DockerService


def docker_available() -> bool:
    """Check if Docker daemon is reachable."""
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not docker_available(),
    reason="Docker daemon not available",
)


@pytest.fixture
def docker_service() -> DockerService:
    return DockerService()


class TestDockerService:
    """Tests for the Docker sandbox execution service."""

    @pytest.mark.asyncio
    async def test_simple_print(self, docker_service: DockerService):
        result = await docker_service.run_code('print("hello")')
        assert result.stdout.strip() == "hello"
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_math_computation(self, docker_service: DockerService):
        result = await docker_service.run_code("print(2 ** 10)")
        assert result.stdout.strip() == "1024"
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_stderr_capture(self, docker_service: DockerService):
        result = await docker_service.run_code(
            'import sys; print("err", file=sys.stderr)'
        )
        assert "err" in result.stderr
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self, docker_service: DockerService):
        result = await docker_service.run_code("raise RuntimeError('boom')")
        assert result.exit_code != 0
        assert "boom" in result.stderr

    @pytest.mark.asyncio
    async def test_timeout(self, docker_service: DockerService):
        result = await docker_service.run_code(
            "import time; time.sleep(30)", timeout=2
        )
        assert result.status == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_stdin_input(self, docker_service: DockerService):
        result = await docker_service.run_code(
            'x = input(); print(f"got: {x}")', stdin="test-input"
        )
        assert "got: test-input" in result.stdout

    @pytest.mark.asyncio
    async def test_no_network_access(self, docker_service: DockerService):
        result = await docker_service.run_code(
            "import socket; socket.create_connection(('google.com', 80), timeout=2)"
        )
        assert result.exit_code != 0  # Should fail — no network

    @pytest.mark.asyncio
    async def test_read_only_filesystem(self, docker_service: DockerService):
        result = await docker_service.run_code(
            "open('/tmp/test.txt', 'w').write('hack')"
        )
        assert result.exit_code != 0  # Should fail — read-only FS
