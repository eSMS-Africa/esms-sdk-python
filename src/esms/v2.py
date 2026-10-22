"""Campaigns, imports, contacts, groups and templates (API v2 surface).

Methods return the API JSON (dicts). Keyword arguments use the API's own
snake_case names; ``None`` values are dropped."""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING, Any, BinaryIO, Dict, List, Optional, Union

if TYPE_CHECKING:  # pragma: no cover
    from .client import Esms


def _q(v: Any) -> str:
    import urllib.parse
    return urllib.parse.quote(str(v), safe="")


class CampaignsResource:
    """draft -> preview / prepare / review -> test -> launch, plus reports."""

    def __init__(self, client: "Esms") -> None:
        self._c = client

    def create(self, *, idempotency_key: Optional[str] = None, **fields: Any) -> Dict[str, Any]:
        """Create a draft (``launch=True`` creates and launches)."""
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._c._request("POST", "/campaigns", body=fields, headers=headers)

    def list(self, *, status: Optional[str] = None, q: Optional[str] = None, tag: Optional[str] = None,
             page: Optional[int] = None, limit: Optional[int] = None, include_runs: Optional[bool] = None) -> Dict[str, Any]:
        return self._c._request("GET", "/campaigns", params={
            "status": status, "q": q, "tag": tag, "page": page, "limit": limit,
            "include_runs": None if include_runs is None else str(include_runs).lower()})

    def get(self, campaign_id: int) -> Dict[str, Any]:
        return self._c._request("GET", f"/campaigns/{_q(campaign_id)}")

    def update(self, campaign_id: int, **fields: Any) -> Dict[str, Any]:
        """Partial update of a draft."""
        return self._c._request("PATCH", f"/campaigns/{_q(campaign_id)}", body=fields)

    def delete(self, campaign_id: int) -> Dict[str, Any]:
        return self._c._request("DELETE", f"/campaigns/{_q(campaign_id)}")

    def preview(self, campaign_id: int, *, text: Optional[str] = None, n: Optional[int] = None) -> Dict[str, Any]:
        return self._post(campaign_id, "preview", {"text": text, "n": n})

    def prepare(self, campaign_id: int) -> Dict[str, Any]:
        """Build the recipient list and exact estimate (status ready | preparing)."""
        return self._post(campaign_id, "prepare")

    def review(self, campaign_id: int) -> Dict[str, Any]:
        return self._c._request("GET", f"/campaigns/{_q(campaign_id)}/review")

    def test(self, campaign_id: int, to: List[str]) -> Dict[str, Any]:
        """Send the first rendered message to up to 3 of your own numbers."""
        return self._post(campaign_id, "test", {"to": to})

    def launch(self, campaign_id: int) -> Dict[str, Any]:
        """Send now, schedule, or submit for approval."""
        return self._post(campaign_id, "launch")

    def approve(self, campaign_id: int, note: Optional[str] = None) -> Dict[str, Any]:
        return self._post(campaign_id, "approve", {"note": note})

    def reject(self, campaign_id: int, note: Optional[str] = None) -> Dict[str, Any]:
        return self._post(campaign_id, "reject", {"note": note})

    def pause(self, campaign_id: int) -> Dict[str, Any]:
        return self._post(campaign_id, "pause")

    def resume(self, campaign_id: int) -> Dict[str, Any]:
        return self._post(campaign_id, "resume")

    def cancel(self, campaign_id: int) -> Dict[str, Any]:
        return self._post(campaign_id, "cancel")

    def retry_failed(self, campaign_id: int) -> Dict[str, Any]:
        """Send again to recipients whose message failed (charged like a new send)."""
        return self._post(campaign_id, "retry-failed")

    def duplicate(self, campaign_id: int) -> Dict[str, Any]:
        return self._post(campaign_id, "duplicate")

    def report(self, campaign_id: int) -> Dict[str, Any]:
        return self._c._request("GET", f"/campaigns/{_q(campaign_id)}/report")

    def stats(self, campaign_id: int) -> Dict[str, Any]:
        return self._c._request("GET", f"/campaigns/{_q(campaign_id)}/stats")

    def recipients(self, campaign_id: int, *, status: Optional[str] = None, country: Optional[str] = None,
                   q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """Per-recipient status. status: delivered | failed | sent | pending | skipped | cancelled."""
        return self._c._request("GET", f"/campaigns/{_q(campaign_id)}/recipients", params={
            "status": status, "country": country, "q": q, "page": page, "limit": limit})

    def runs(self, campaign_id: int) -> Dict[str, Any]:
        return self._c._request("GET", f"/campaigns/{_q(campaign_id)}/runs")

    def _post(self, campaign_id: int, action: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._c._request("POST", f"/campaigns/{_q(campaign_id)}/{action}", body=body)


class ImportsResource:
    """Recipient imports: CSV / Excel upload, paste, Google Sheets."""

    def __init__(self, client: "Esms") -> None:
        self._c = client

    def upload(self, file: Union[str, bytes, BinaryIO], *, filename: Optional[str] = None,
               default_country: Optional[str] = None) -> Dict[str, Any]:
        """Upload a CSV/XLSX/XLS file: a path, bytes, or an open binary file."""
        if isinstance(file, str):
            filename = filename or os.path.basename(file)
            with open(file, "rb") as fh:
                data = fh.read()
        elif isinstance(file, (bytes, bytearray)):
            data = bytes(file)
        else:
            data = file.read()
            filename = filename or os.path.basename(getattr(file, "name", "") or "") or None
        filename = filename or "upload.csv"
        boundary = "esms" + uuid.uuid4().hex
        parts = []
        if default_country:
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="default_country"\r\n\r\n'
                         f"{default_country}\r\n".encode())
        safe = filename.replace('"', "")
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{safe}"\r\n'
                     f"Content-Type: application/octet-stream\r\n\r\n".encode() + data + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        return self._c._request("POST", "/imports", raw=b"".join(parts),
                                content_type=f"multipart/form-data; boundary={boundary}")

    def paste(self, text: str, *, default_country: Optional[str] = None) -> Dict[str, Any]:
        return self._c._request("POST", "/imports/paste", body={"text": text, "default_country": default_country})

    def gsheet(self, url: str, *, default_country: Optional[str] = None) -> Dict[str, Any]:
        return self._c._request("POST", "/imports/gsheet", body={"url": url, "default_country": default_country})

    def get(self, import_id: str) -> Dict[str, Any]:
        return self._c._request("GET", f"/imports/{_q(import_id)}")

    def process(self, import_id: str, *, mapping: Dict[str, Any], default_country: Optional[str] = None,
                dedupe: Optional[bool] = None, skip_opted_out: Optional[bool] = None) -> Dict[str, Any]:
        """Validate in the background. mapping = {"phone": col, "name": col, "fields": {col: key}}."""
        return self._c._request("POST", f"/imports/{_q(import_id)}/process", body={
            "mapping": mapping, "default_country": default_country, "dedupe": dedupe,
            "skip_opted_out": skip_opted_out})

    def errors(self, import_id: str, *, reason: Optional[str] = None, page: Optional[int] = None,
               limit: Optional[int] = None) -> Dict[str, Any]:
        return self._c._request("GET", f"/imports/{_q(import_id)}/errors",
                                params={"reason": reason, "page": page, "limit": limit})

    def recipients(self, import_id: str, *, page: Optional[int] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        return self._c._request("GET", f"/imports/{_q(import_id)}/recipients", params={"page": page, "limit": limit})

    def save_to_group(self, import_id: str, *, group_id: Optional[int] = None, name: Optional[str] = None,
                      tags: Optional[List[str]] = None) -> Dict[str, Any]:
        return self._c._request("POST", f"/imports/{_q(import_id)}/save-to-group",
                                body={"group_id": group_id, "name": name, "tags": tags})


class JobsResource:
    def __init__(self, client: "Esms") -> None:
        self._c = client

    def get(self, job_id: int) -> Dict[str, Any]:
        return self._c._request("GET", f"/jobs/{_q(job_id)}")


class ContactsResource:
    """Contact book: everyone across your groups, addressed by E.164 phone."""

    def __init__(self, client: "Esms") -> None:
        self._c = client

    def list(self, *, search: Optional[str] = None, group_id: Optional[int] = None,
             opted_out: Optional[bool] = None, page: Optional[int] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        return self._c._request("GET", "/contacts", params={
            "search": search, "group_id": group_id, "page": page, "limit": limit,
            "opted_out": None if opted_out is None else str(opted_out).lower()})

    def get(self, phone: str) -> Dict[str, Any]:
        return self._c._request("GET", f"/contacts/{_q(phone)}")

    def upsert(self, *, phone: str, group_ids: List[int], name: Optional[str] = None,
               fields: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        return self._c._request("POST", "/contacts", body={"phone": phone, "group_ids": group_ids,
                                                           "name": name, "fields": fields})

    def update(self, phone: str, *, new_phone: Optional[str] = None, name: Optional[str] = None,
               fields: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        return self._c._request("PATCH", f"/contacts/{_q(phone)}",
                                body={"phone": new_phone, "name": name, "fields": fields})

    def delete(self, phone: str) -> None:
        self._c._request("DELETE", f"/contacts/{_q(phone)}")


class GroupsResource:
    def __init__(self, client: "Esms") -> None:
        self._c = client

    def list(self, *, q: Optional[str] = None) -> Dict[str, Any]:
        return self._c._request("GET", "/groups", params={"q": q})

    def create(self, name: str, *, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        return self._c._request("POST", "/groups", body={"name": name, "tags": tags})

    def get(self, group_id: int) -> Dict[str, Any]:
        return self._c._request("GET", f"/groups/{_q(group_id)}")

    def update(self, group_id: int, *, name: Optional[str] = None, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        return self._c._request("PATCH", f"/groups/{_q(group_id)}", body={"name": name, "tags": tags})

    def delete(self, group_id: int) -> Dict[str, Any]:
        return self._c._request("DELETE", f"/groups/{_q(group_id)}")

    def contacts(self, group_id: int, *, search: Optional[str] = None, page: Optional[int] = None,
                 limit: Optional[int] = None) -> Dict[str, Any]:
        return self._c._request("GET", f"/groups/{_q(group_id)}/contacts",
                                params={"search": search, "page": page, "limit": limit})

    def add_contacts(self, group_id: int, contacts: List[Dict[str, Any]], *,
                     default_country: Optional[str] = None) -> Dict[str, Any]:
        """Add up to 10,000 contacts [{"phone", "name", "fields"}]."""
        return self._c._request("POST", f"/groups/{_q(group_id)}/contacts",
                                body={"contacts": contacts, "default_country": default_country})

    def remove_contact(self, group_id: int, phone: str) -> Dict[str, Any]:
        return self._c._request("DELETE", f"/groups/{_q(group_id)}/contacts/{_q(phone)}")


class TemplatesResource:
    def __init__(self, client: "Esms") -> None:
        self._c = client

    def list(self, *, category: Optional[str] = None, message_type: Optional[str] = None,
             q: Optional[str] = None) -> Dict[str, Any]:
        return self._c._request("GET", "/templates", params={"category": category, "message_type": message_type, "q": q})

    def create(self, *, name: str, text: str, **fields: Any) -> Dict[str, Any]:
        """fields: category, message_type, description, visibility (team|private), sender_id."""
        return self._c._request("POST", "/templates", body={"name": name, "text": text, **fields})

    def get(self, template_id: int) -> Dict[str, Any]:
        return self._c._request("GET", f"/templates/{_q(template_id)}")

    def update(self, template_id: int, **fields: Any) -> Dict[str, Any]:
        """Partial update."""
        return self._c._request("PATCH", f"/templates/{_q(template_id)}", body=fields)

    def delete(self, template_id: int) -> None:
        self._c._request("DELETE", f"/templates/{_q(template_id)}")

    def starter_pack(self) -> Dict[str, Any]:
        return self._c._request("GET", "/templates/starter-pack")

    def use_starter(self, key: str) -> Dict[str, Any]:
        """Copy a starter template (e.g. "payment-reminder") into your library."""
        return self._c._request("POST", f"/templates/starter-pack/{_q(key)}")

    def render(self, text: str, *, vars: Optional[Dict[str, str]] = None, name: Optional[str] = None,
               phone: Optional[str] = None) -> Dict[str, Any]:
        return self._c._request("POST", "/templates/render", body={"text": text, "vars": vars, "name": name, "phone": phone})
