from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.e2e_stack
def test_compose_stack_smoke() -> None:
    if not os.getenv("BUSINESS_AGENT_RUN_STACK_E2E"):
        pytest.skip("Set BUSINESS_AGENT_RUN_STACK_E2E=1 to run the docker-compose stack E2E smoke test")

    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker is not available in this environment")

    repo_root = Path(__file__).resolve().parents[1]
    compose_cmd = [docker, "compose"]

    result = subprocess.run(compose_cmd + ["config", "--services"], cwd=repo_root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    services = set(result.stdout.splitlines())
    assert {"app", "worker", "redis", "qdrant", "postgres"}.issubset(services)
