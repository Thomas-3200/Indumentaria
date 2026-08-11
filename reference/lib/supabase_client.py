"""
lib/supabase_client.py
─────────────────────────────────────────────────────────────────────────
Supabase REST + Storage wrapper — shared across all StepFlow modules.

Reads from environment:
  SUPABASE_URL   e.g. https://frurqigartxzikptdrpx.supabase.co
  SUPABASE_KEY   service_role JWT

Usage:
  from lib import SupabaseClient
  db = SupabaseClient()
  rows = db.select("intake_batches", filters={"client_id": "amapola"})
─────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import mimetypes
import os
import logging
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)


# ── Exceptions ─────────────────────────────────────────────────────────────────

class SupabaseError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Supabase {status_code}: {message}")


# ── Client ─────────────────────────────────────────────────────────────────────

class SupabaseClient:
    """
    Supabase REST API + Storage client.
    Does NOT use supabase-py — plain requests to keep dependencies minimal.
    Thread-safe (stateless per request).
    """

    def __init__(
        self,
        url: str | None = None,
        key: str | None = None,
        timeout: int = 60,
    ):
        self.url     = (url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
        self.key     = key or os.environ.get("SUPABASE_KEY", "")
        self.timeout = timeout

        if not self.url:
            raise EnvironmentError("SUPABASE_URL is not set.")
        if not self.key:
            raise EnvironmentError("SUPABASE_KEY is not set.")

        self._headers = {
            "apikey":        self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type":  "application/json",
        }

    # ── Internal ───────────────────────────────────────────────────────────────

    def _rest_url(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"

    def _storage_url(self, bucket: str, path: str = "") -> str:
        base = f"{self.url}/storage/v1/object/{bucket}"
        return f"{base}/{path}" if path else base

    def _raise_for_status(self, resp: requests.Response) -> None:
        if not resp.ok:
            raise SupabaseError(resp.status_code, resp.text[:400])

    # ── REST — SELECT ──────────────────────────────────────────────────────────

    def select(
        self,
        table:   str,
        filters: dict | None = None,
        columns: str = "*",
        order:   str | None = None,
        limit:   int | None = None,
        offset:  int | None = None,
    ) -> list[dict]:
        """
        SELECT rows from a table.
        filters: {"column": "value"}  → exact match (eq)
        For complex filters pass raw PostgREST params via filters:
          {"status": "neq.published"}
        """
        params: dict[str, Any] = {"select": columns}
        if filters:
            for col, val in filters.items():
                # Allow raw PostgREST operators: "neq.published", "gt.100", etc.
                if "." in str(val) and any(
                    str(val).startswith(op + ".")
                    for op in ("eq","neq","lt","lte","gt","gte","like","ilike","is")
                ):
                    params[col] = val
                else:
                    params[col] = f"eq.{val}"
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset

        resp = requests.get(
            self._rest_url(table), headers=self._headers,
            params=params, timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json() or []

    def select_one(self, table: str, filters: dict) -> dict | None:
        rows = self.select(table, filters=filters, limit=1)
        return rows[0] if rows else None

    # ── REST — INSERT ──────────────────────────────────────────────────────────

    def insert(self, table: str, data: dict | list[dict]) -> dict | list[dict]:
        """INSERT one or many rows. Returns inserted row(s)."""
        headers = {**self._headers, "Prefer": "return=representation"}
        resp = requests.post(
            self._rest_url(table), headers=headers,
            json=data, timeout=self.timeout,
        )
        self._raise_for_status(resp)
        result = resp.json()
        # Single dict input → return single dict
        if isinstance(data, dict) and isinstance(result, list):
            return result[0] if result else {}
        return result

    # ── REST — UPDATE ──────────────────────────────────────────────────────────

    def update(self, table: str, data: dict, filters: dict) -> list[dict]:
        """PATCH rows matching filters. Returns updated rows."""
        headers = {**self._headers, "Prefer": "return=representation"}
        params  = {col: f"eq.{val}" for col, val in filters.items()}
        resp = requests.patch(
            self._rest_url(table), headers=headers,
            json=data, params=params, timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json() or []

    # ── REST — UPSERT ─────────────────────────────────────────────────────────

    def upsert(
        self,
        table:       str,
        data:        dict | list[dict],
        on_conflict: str = "id",
    ) -> list[dict]:
        """INSERT or UPDATE on conflict. Returns affected rows."""
        headers = {
            **self._headers,
            "Prefer": f"resolution=merge-duplicates,return=representation",
        }
        resp = requests.post(
            self._rest_url(table), headers=headers,
            json=data, params={"on_conflict": on_conflict},
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json() or []

    # ── REST — DELETE ──────────────────────────────────────────────────────────

    def delete(self, table: str, filters: dict) -> list[dict]:
        """DELETE rows matching filters. Returns deleted rows."""
        headers = {**self._headers, "Prefer": "return=representation"}
        params  = {col: f"eq.{val}" for col, val in filters.items()}
        resp = requests.delete(
            self._rest_url(table), headers=headers,
            params=params, timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json() or []

    # ── Storage — UPLOAD ───────────────────────────────────────────────────────

    def upload_bytes(
        self,
        bucket:       str,
        storage_path: str,
        data:         bytes,
        content_type: str | None = None,
        upsert:       bool = False,
    ) -> str:
        """
        Upload raw bytes to Supabase Storage.
        Returns the public URL.
        """
        if not content_type:
            guessed, _ = mimetypes.guess_type(storage_path)
            content_type = guessed or "application/octet-stream"

        headers: dict[str, str] = {
            "apikey":        self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type":  content_type,
        }
        if upsert:
            headers["x-upsert"] = "true"

        url  = self._storage_url(bucket, storage_path)
        resp = requests.post(url, headers=headers, data=data, timeout=120)

        if resp.status_code in (200, 201):
            return self.public_url(bucket, storage_path)
        if resp.status_code == 400 and "already exists" in resp.text:
            return self.public_url(bucket, storage_path)
        raise SupabaseError(resp.status_code, resp.text[:400])

    def upload_file(
        self,
        bucket:       str,
        storage_path: str,
        local_path:   str | Path,
        upsert:       bool = False,
    ) -> str:
        """Upload a local file to Supabase Storage. Returns public URL."""
        p = Path(local_path)
        content_type, _ = mimetypes.guess_type(str(p))
        with open(p, "rb") as f:
            return self.upload_bytes(
                bucket, storage_path, f.read(),
                content_type=content_type, upsert=upsert,
            )

    # ── Storage — DOWNLOAD ─────────────────────────────────────────────────────

    def download_bytes(self, bucket: str, storage_path: str) -> bytes:
        """Download a file from Supabase Storage. Returns raw bytes."""
        url = self._storage_url(bucket, storage_path)
        resp = requests.get(
            url,
            headers={"apikey": self.key, "Authorization": f"Bearer {self.key}"},
            timeout=120,
        )
        self._raise_for_status(resp)
        return resp.content

    def download_to_file(
        self, bucket: str, storage_path: str, local_path: str | Path
    ) -> Path:
        """Download a Storage object to a local file."""
        data = self.download_bytes(bucket, storage_path)
        p    = Path(local_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    # ── Storage — UTILS ────────────────────────────────────────────────────────

    def public_url(self, bucket: str, storage_path: str) -> str:
        """Return the public URL for a storage object (no auth required)."""
        return f"{self.url}/storage/v1/object/public/{bucket}/{storage_path}"

    def delete_file(self, bucket: str, storage_path: str) -> bool:
        """Delete a single file from Storage. Returns True on success."""
        url  = f"{self.url}/storage/v1/object/{bucket}"
        resp = requests.delete(
            url, headers=self._headers,
            json={"prefixes": [storage_path]}, timeout=self.timeout,
        )
        return resp.ok

    def list_files(self, bucket: str, prefix: str = "") -> list[dict]:
        """List files under a bucket/prefix."""
        url  = f"{self.url}/storage/v1/object/list/{bucket}"
        resp = requests.post(
            url, headers=self._headers,
            json={"prefix": prefix, "limit": 1000}, timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json() or []

    def ensure_bucket(self, bucket: str, public: bool = True) -> None:
        """Create a bucket if it does not already exist (idempotent)."""
        resp = requests.post(
            f"{self.url}/storage/v1/bucket",
            headers=self._headers,
            json={"id": bucket, "name": bucket, "public": public},
            timeout=self.timeout,
        )
        if resp.status_code not in (200, 201, 409):
            raise SupabaseError(resp.status_code, resp.text[:400])

    # ── Health ─────────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        try:
            resp = requests.get(
                f"{self.url}/rest/v1/",
                headers=self._headers, timeout=10,
            )
            return resp.status_code < 500
        except Exception as exc:
            log.warning("Supabase health check failed: %s", exc)
            return False
