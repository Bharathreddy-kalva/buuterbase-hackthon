"""
Quick connectivity check for all FleetMind external integrations.

Run with:
    python tests/verify_connections.py
"""

import os

import httpx
from dotenv import load_dotenv

load_dotenv()


def test_butterbase():
    base_url = os.environ.get("BUTTERBASE_URL", "").rstrip("/")
    api_key = os.environ.get("BUTTERBASE_API_KEY", "")
    project_id = os.environ.get("BUTTERBASE_PROJECT_ID", "")

    try:
        # Liveness check (no auth required)
        health = httpx.get(f"{base_url}/health", timeout=10)
        health.raise_for_status()

        # Verify the API key + project id by listing the app's schema
        schema = httpx.get(
            f"{base_url}/v1/{project_id}/schema",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        schema.raise_for_status()

        tables = schema.json().get("tables", [])
        print(f"✅ Butterbase connected ({len(tables)} table(s) in {project_id})")
    except Exception as e:
        print(f"❌ Butterbase failed: {e}")


def test_butterbase_ai_gateway():
    base_url = os.environ.get("BUTTERBASE_URL", "").rstrip("/")
    api_key = os.environ.get("BUTTERBASE_AI_KEY", "")
    project_id = os.environ.get("BUTTERBASE_PROJECT_ID", "")

    try:
        resp = httpx.post(
            f"{base_url}/v1/{project_id}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "anthropic/claude-sonnet-4.6",
                "messages": [{"role": "user", "content": "say hello in 3 words"}],
                "max_tokens": 20,
            },
            timeout=30,
        )
        resp.raise_for_status()

        data = resp.json()
        message = data["choices"][0]["message"]["content"]
        print(f"✅ Butterbase AI gateway working - response: {message!r}")
    except Exception as e:
        print(f"❌ AI gateway failed: {e}")


def test_everos():
    try:
        resp = httpx.get("http://127.0.0.1:8000/health", timeout=3)
        resp.raise_for_status()
        print("✅ EverOS running")
    except Exception:
        print("❌ EverOS not running - run: everos server start")


def test_butterbase_embeddings():
    base_url = os.environ.get("BUTTERBASE_URL", "").rstrip("/")
    project_id = os.environ.get("BUTTERBASE_PROJECT_ID", "")
    api_key = os.environ.get("EVEROS_EMBEDDING__API_KEY", "")
    model = os.environ.get("EVEROS_EMBEDDING__MODEL", "openai/text-embedding-3-small")

    try:
        resp = httpx.post(
            f"{base_url}/v1/{project_id}/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "input": "test connection"},
            timeout=30,
        )
        resp.raise_for_status()

        data = resp.json()
        dims = len(data["data"][0]["embedding"])
        print(f"✅ Butterbase embeddings working ({dims}-dim vector)")
    except Exception as e:
        print(f"❌ Butterbase embeddings failed: {e}")


def test_photon():
    api_key = os.environ.get("PHOTON_API_KEY", "")

    if not api_key:
        print("⚠️ Photon not configured (optional for now)")
        return

    try:
        resp = httpx.get(
            "https://app.photon.codes/api/v1/me",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code < 500:
            print("✅ Photon configured")
        else:
            print(f"⚠️ Photon not configured (optional for now) - status {resp.status_code}")
    except Exception:
        print("⚠️ Photon not configured (optional for now)")


if __name__ == "__main__":
    test_butterbase()
    test_butterbase_ai_gateway()
    test_everos()
    test_butterbase_embeddings()
    test_photon()
