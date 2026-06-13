"""Thin REST client for the Butterbase Data API.

All Butterbase table access in FleetMind should go through this module
rather than calling the HTTP API directly.
"""

import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

BUTTERBASE_URL = os.environ.get("BUTTERBASE_URL", "").rstrip("/")
BUTTERBASE_API_KEY = os.environ.get("BUTTERBASE_API_KEY", "")
BUTTERBASE_PROJECT_ID = os.environ.get("BUTTERBASE_PROJECT_ID", "")
BUTTERBASE_AI_KEY = os.environ.get("BUTTERBASE_AI_KEY", BUTTERBASE_API_KEY)

DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"


def _headers():
    return {"Authorization": f"Bearer {BUTTERBASE_API_KEY}"}


def _table_url(table, row_id=None):
    url = f"{BUTTERBASE_URL}/v1/{BUTTERBASE_PROJECT_ID}/{table}"
    if row_id is not None:
        url += f"/{row_id}"
    return url


def select(table, params=None):
    """List rows from a table, with optional filter/sort/pagination params."""
    resp = httpx.get(_table_url(table), headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def insert(table, data):
    """Insert a row into a table and return the created row."""
    resp = httpx.post(_table_url(table), headers=_headers(), json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def update(table, row_id, data):
    """Update a row by primary key and return the updated row."""
    resp = httpx.patch(_table_url(table, row_id), headers=_headers(), json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def delete(table, row_id):
    """Delete a row by primary key."""
    resp = httpx.delete(_table_url(table, row_id), headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def chat_completion(messages, model=DEFAULT_MODEL, max_tokens=1024, temperature=0.3):
    """Call the Butterbase AI gateway's chat completions endpoint."""
    resp = httpx.post(
        f"{BUTTERBASE_URL}/v1/{BUTTERBASE_PROJECT_ID}/chat/completions",
        headers={"Authorization": f"Bearer {BUTTERBASE_AI_KEY}"},
        json={
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def chat_completion_json(system_prompt, user_prompt, model=DEFAULT_MODEL, max_tokens=1024):
    """Call the AI gateway and parse a JSON object out of its response."""
    content = chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model=model,
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return _extract_json(content)


def _extract_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in model response: {text!r}")
    return json.loads(text[start : end + 1])
