"""Static deployment-contract tests.

Docker is not required in the development test environment.  These checks guard
the critical first-boot contract that a named /app/data volume must not hide the
versioned seed files baked into the backend image.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_backend_image_keeps_bootstrap_seed_outside_runtime_volume() -> None:
    dockerfile = (PROJECT_ROOT / "deploy" / "backend.Dockerfile").read_text(encoding="utf-8")
    entrypoint = (PROJECT_ROOT / "deploy" / "backend-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "COPY data/seed /app/bootstrap-seed" in dockerfile
    assert "- skilltwin_data:/app/data" in compose
    assert "BOOTSTRAP_SEED_DIR=/app/bootstrap-seed" in entrypoint
    assert "cp -R \"$BOOTSTRAP_SEED_DIR\"/. /app/data/seed/" in entrypoint
    assert entrypoint.index("cp -R") < entrypoint.index("python /app/scripts/seed_skills.py")


def test_deployment_keeps_frontend_and_api_on_one_origin() -> None:
    nginx = (PROJECT_ROOT / "deploy" / "nginx" / "default.conf").read_text(encoding="utf-8")

    assert "location /api/" in nginx
    assert "proxy_pass http://backend:8000" in nginx
    assert "try_files $uri $uri/ /index.html" in nginx
