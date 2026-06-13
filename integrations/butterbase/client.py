"""Thin REST client for the Butterbase Data API.

All Butterbase table access in FleetMind should go through this module
rather than calling the HTTP API directly.
"""

import os

import httpx
from dotenv import load_dotenv

load_dotenv()

BUTTERBASE_URL = os.environ.get("BUTTERBASE_URL", "").rstrip("/")
BUTTERBASE_API_KEY = os.environ.get("BUTTERBASE_API_KEY", "")
BUTTERBASE_PROJECT_ID = os.environ.get("BUTTERBASE_PROJECT_ID", "")


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
