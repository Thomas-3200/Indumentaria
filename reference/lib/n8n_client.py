"""
lib/n8n_client.py
─────────────────────────────────────────────────────────────────────────
n8n REST API wrapper — shared across all StepFlow modules.

Reads from environment:
  N8N_BASE_URL   e.g. https://n8n.agenciaiasm.online
  N8N_API_KEY    e.g. eyJhbGci...

Usage:
  from lib import N8NClient
  n8n = N8NClient()
  wf  = n8n.get_workflow("QIy2xgi1RcF6PCMA")
─────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import os
import logging
from typing import Any

import requests

log = logging.getLogger(__name__)


# ── Exceptions ─────────────────────────────────────────────────────────────────

class N8NError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"n8n API {status_code}: {message}")


# ── Client ─────────────────────────────────────────────────────────────────────

class N8NClient:
    """
    Thin wrapper around the n8n public REST API.
    Thread-safe (each call creates its own requests.Session internally).
    Does NOT cache responses — callers are responsible for caching if needed.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key:  str | None = None,
        timeout:  int = 30,
    ):
        self.base_url = (base_url or os.environ.get("N8N_BASE_URL", "")).rstrip("/")
        self.api_key  = api_key  or os.environ.get("N8N_API_KEY",  "")
        self.timeout  = timeout

        if not self.base_url:
            raise EnvironmentError("N8N_BASE_URL is not set.")
        if not self.api_key:
            raise EnvironmentError("N8N_API_KEY is not set.")

        self._headers = {
            "X-N8N-API-KEY": self.api_key,
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

    # ── Internal ───────────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v1{path}"

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url  = self._url(path)
        resp = requests.request(
            method, url, headers=self._headers, timeout=self.timeout, **kwargs
        )
        if not resp.ok:
            raise N8NError(resp.status_code, resp.text[:400])
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    # ── Workflows ──────────────────────────────────────────────────────────────

    def get_workflow(self, workflow_id: str) -> dict:
        """Fetch a single workflow by ID."""
        return self._request("GET", f"/workflows/{workflow_id}")

    def list_workflows(self, limit: int = 100) -> list[dict]:
        """List all workflows in the instance."""
        data = self._request("GET", f"/workflows?limit={limit}")
        return data.get("data", [])

    def create_workflow(self, payload: dict) -> dict:
        """
        Create a new workflow.
        Automatically strips the 'active' field (n8n read-only on creation).
        """
        clean = {k: v for k, v in payload.items() if k != "active"}
        return self._request("POST", "/workflows", json=clean)

    def update_workflow(self, workflow_id: str, payload: dict) -> dict:
        """
        Full PUT replacement of a workflow.
        Automatically strips read-only fields.
        """
        read_only = {"active", "id", "createdAt", "updatedAt", "versionId"}
        clean = {k: v for k, v in payload.items() if k not in read_only}
        return self._request("PUT", f"/workflows/{workflow_id}", json=clean)

    def delete_workflow(self, workflow_id: str) -> dict:
        return self._request("DELETE", f"/workflows/{workflow_id}")

    def activate_workflow(self, workflow_id: str) -> dict:
        return self._request("POST", f"/workflows/{workflow_id}/activate")

    def deactivate_workflow(self, workflow_id: str) -> dict:
        return self._request("POST", f"/workflows/{workflow_id}/deactivate")

    def workflow_node_count(self, workflow_id: str) -> int:
        """Quick check: how many nodes does a workflow have? Used in regression tests."""
        wf = self.get_workflow(workflow_id)
        return len(wf.get("nodes", []))

    # ── Executions ─────────────────────────────────────────────────────────────

    def list_executions(
        self,
        workflow_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        params: list[str] = [f"limit={limit}"]
        if workflow_id:
            params.append(f"workflowId={workflow_id}")
        if status:
            params.append(f"status={status}")
        qs = "&".join(params)
        data = self._request("GET", f"/executions?{qs}")
        return data.get("data", [])

    def get_execution(self, execution_id: str) -> dict:
        return self._request("GET", f"/executions/{execution_id}")

    def delete_execution(self, execution_id: str) -> dict:
        return self._request("DELETE", f"/executions/{execution_id}")

    # ── Webhooks ───────────────────────────────────────────────────────────────

    def trigger_webhook(
        self,
        webhook_path: str,
        payload: dict,
        method: str = "POST",
    ) -> dict:
        """
        Trigger an n8n webhook workflow directly (bypasses API auth).
        webhook_path example: "intake/amapola" → hits /webhook/intake/amapola
        """
        url  = f"{self.base_url}/webhook/{webhook_path.lstrip('/')}"
        resp = requests.request(method, url, json=payload, timeout=self.timeout)
        if not resp.ok:
            raise N8NError(resp.status_code, resp.text[:400])
        return resp.json() if resp.content else {}

    # ── Credentials ────────────────────────────────────────────────────────────

    def list_credentials(self) -> list[dict]:
        data = self._request("GET", "/credentials")
        return data.get("data", [])

    # ── Health ─────────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Returns True if n8n is reachable and the API key is valid."""
        try:
            self._request("GET", "/workflows?limit=1")
            return True
        except Exception as exc:
            log.warning("n8n health check failed: %s", exc)
            return False
