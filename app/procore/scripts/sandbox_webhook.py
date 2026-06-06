"""
@milehigh-header
schema_version: 1
purpose: Short-term, verbose Procore webhook tool for pointing a single project's Submittals webhook at the milehigh SANDBOX app, for end-to-end testing of the DRR/Rel flow.
exports:
  main: CLI entry point (list / create / delete) for one project's sandbox webhook.
imports_from: [argparse, app, app.config, app.procore.api]
imported_by: []
invariants:
  - Targets PROD Procore (api.procore.com) with the prod company + app credentials; only the
    webhook destination_url points at the milehigh sandbox deployment.
  - Reuses an existing hook for the namespace instead of re-creating it (re-creating returns 400
    "namespace has already been taken").
  - Prints the full Procore request body and response (including 4xx bodies) for debugging.

Why this exists: the generic create/ensure scripts hardcode the namespace + payload version and
swallow the Procore error body, which made a 400 on this project hard to diagnose. This script is
intentionally explicit and chatty so we can iterate on sandbox testing quickly.

Usage (run from repo root):
    # Inspect what already exists on the project (no changes)
    python -m app.procore.scripts.sandbox_webhook --list

    # Create / ensure the webhook + Submittals update+create triggers, pointing at sandbox
    python -m app.procore.scripts.sandbox_webhook

    # Delete the existing hook for the namespace (clean slate before re-creating)
    python -m app.procore.scripts.sandbox_webhook --delete

Defaults: project-id 1344700 (PROJ. # 999), destination
https://sandbox-mhmw.onrender.com/procore/webhook, namespace mile-high-metal-works-sandbox
(a distinct namespace so the sandbox hook coexists with the prod hook on the same project).
"""

import argparse
import json

import requests

from app import create_app
from app.config import Config as cfg
from app.procore.api import ProcoreAPI

DEFAULT_PROJECT_ID = 1344700  # PROJ. # 999
DEFAULT_DESTINATION_URL = "https://sandbox-mhmw.onrender.com/procore/webhook"
# A Procore project allows only ONE hook per namespace. The PROD hook already owns
# "mile-high-metal-works" (pointing at the prod app), so the sandbox hook needs its own
# namespace to coexist instead of clobbering prod's destination_url.
DEFAULT_NAMESPACE = "mile-high-metal-works-sandbox"
REQUIRED_EVENT_TYPES = ["update", "create"]


def _pretty(obj) -> str:
    try:
        return json.dumps(obj, indent=2, default=str)
    except (TypeError, ValueError):
        return str(obj)


def _http_detail(exc: Exception) -> str:
    """Extract the most useful detail from a Procore HTTP error, including the response body."""
    resp = getattr(exc, "response", None)
    if resp is not None:
        return f"HTTP {resp.status_code}: {resp.text}"
    return str(exc)


def _base(company_id: int, project_id: int) -> str:
    return f"/rest/v2.0/companies/{company_id}/projects/{project_id}/webhooks/hooks"


def list_hooks(client, company_id, project_id, namespace):
    resp = client._get(f"{_base(company_id, project_id)}?namespace={namespace}")
    if isinstance(resp, dict) and "data" in resp:
        return resp["data"] or []
    if isinstance(resp, list):
        return resp
    return []


def list_triggers(client, company_id, project_id, hook_id):
    resp = client._get(f"{_base(company_id, project_id)}/{hook_id}/triggers")
    if isinstance(resp, dict) and "data" in resp:
        return resp["data"] or []
    if isinstance(resp, list):
        return resp
    return []


def create_hook(client, company_id, project_id, namespace, destination_url, payload_version):
    body = {
        "payload_version": payload_version,
        "namespace": namespace,
        "destination_url": destination_url,
    }
    print(f"POST {_base(company_id, project_id)}")
    print(f"  body: {_pretty(body)}")
    return client._post(_base(company_id, project_id), body)


def create_trigger(client, company_id, project_id, hook_id, event_type):
    body = {"resource_name": "Submittals", "event_type": event_type}
    path = f"{_base(company_id, project_id)}/{hook_id}/triggers"
    print(f"POST {path}")
    print(f"  body: {_pretty(body)}")
    return client._post(path, body)


def delete_hook(client, company_id, project_id, hook_id):
    return client._delete(f"{_base(company_id, project_id)}/{hook_id}")


def _hook_id(hook):
    if isinstance(hook, dict):
        return hook.get("id") or hook.get("hook_id") or hook.get("webhook_id")
    return None


def _existing_trigger_types(triggers):
    # Procore returns event_type uppercased (e.g. "UPDATE"); normalize for comparison.
    found = set()
    for t in triggers:
        if isinstance(t, dict) and t.get("resource_name") == "Submittals":
            et = (t.get("event_type") or "").lower()
            if et in REQUIRED_EVENT_TYPES:
                found.add(et)
    return found


def run(project_id, destination_url, namespace, company_id, payload_version,
        do_list, do_delete, dry_run):
    print("=" * 70)
    print("Procore SANDBOX webhook tool")
    print(f"  Procore host : {ProcoreAPI.BASE_URL}")
    print(f"  company_id   : {company_id}")
    print(f"  project_id   : {project_id}")
    print(f"  namespace    : {namespace}")
    print(f"  destination  : {destination_url}")
    print(f"  mode         : {'list' if do_list else 'delete' if do_delete else 'create/ensure'}"
          f"{' (dry-run)' if dry_run else ''}")
    print("=" * 70)

    client = ProcoreAPI(
        cfg.PROD_PROCORE_CLIENT_ID,
        cfg.PROD_PROCORE_CLIENT_SECRET,
        destination_url,  # used as the hook destination_url
    )

    # 1) Inspect existing hooks for this namespace.
    try:
        hooks = list_hooks(client, company_id, project_id, namespace)
    except requests.HTTPError as e:
        print(f"\n✗ Failed to list hooks: {_http_detail(e)}")
        return 1
    except Exception as e:  # noqa: BLE001 - surface anything during testing
        print(f"\n✗ Failed to list hooks: {e}")
        return 1

    print(f"\nExisting hooks for namespace '{namespace}': {len(hooks)}")
    for h in hooks:
        hid = _hook_id(h)
        print(f"  - hook_id={hid} destination_url={h.get('destination_url') if isinstance(h, dict) else '?'}")
        try:
            trigs = list_triggers(client, company_id, project_id, hid)
            print(f"      triggers: {[ (t.get('resource_name'), t.get('event_type')) for t in trigs if isinstance(t, dict)]}")
        except Exception as e:  # noqa: BLE001
            print(f"      (could not list triggers: {_http_detail(e)})")

    if do_list:
        return 0

    # 2) Delete mode: remove existing hooks for the namespace.
    if do_delete:
        if not hooks:
            print("\nNothing to delete.")
            return 0
        for h in hooks:
            hid = _hook_id(h)
            if dry_run:
                print(f"[dry-run] would delete hook {hid}")
                continue
            try:
                delete_hook(client, company_id, project_id, hid)
                print(f"✓ Deleted hook {hid}")
            except Exception as e:  # noqa: BLE001
                print(f"✗ Failed to delete hook {hid}: {_http_detail(e)}")
        return 0

    # 3) Create/ensure mode.
    existing = hooks[0] if hooks else None
    hook_id = _hook_id(existing) if existing else None

    if hook_id:
        existing_dest = existing.get("destination_url") if isinstance(existing, dict) else None
        print(f"\nReusing existing hook {hook_id} (not re-creating; that would 400 'namespace taken').")
        if existing_dest and existing_dest != destination_url:
            print("  ⚠ WARNING: this hook's destination_url does NOT match the requested URL:")
            print(f"      existing : {existing_dest}")
            print(f"      requested: {destination_url}")
            print("    Pick a namespace that isn't already used by another deployment "
                  "(see --namespace), or --delete this hook first. Refusing to touch it.")
            return 1
    else:
        if dry_run:
            print(f"\n[dry-run] would create hook -> {destination_url} with triggers {REQUIRED_EVENT_TYPES}")
            return 0
        try:
            resp = create_hook(client, company_id, project_id, namespace, destination_url, payload_version)
            print(f"  response: {_pretty(resp)}")
            data = resp.get("data", resp) if isinstance(resp, dict) else {}
            hook_id = _hook_id(data) or _hook_id(resp)
            if not hook_id:
                print(f"✗ Hook created but no id found in response.")
                return 1
            print(f"✓ Created hook {hook_id}")
        except Exception as e:  # noqa: BLE001
            print(f"✗ Failed to create hook: {_http_detail(e)}")
            return 1

    # Ensure both triggers exist.
    try:
        existing_types = _existing_trigger_types(list_triggers(client, company_id, project_id, hook_id))
    except Exception as e:  # noqa: BLE001
        print(f"✗ Failed to list triggers for hook {hook_id}: {_http_detail(e)}")
        return 1

    missing = [et for et in REQUIRED_EVENT_TYPES if et not in existing_types]
    if not missing:
        print(f"\n✓ Hook {hook_id} already has triggers {sorted(existing_types)} -> nothing to do.")
        return 0

    print(f"\nMissing triggers: {missing}")
    for et in missing:
        if dry_run:
            print(f"[dry-run] would create trigger '{et}'")
            continue
        try:
            resp = create_trigger(client, company_id, project_id, hook_id, et)
            print(f"  response: {_pretty(resp)}")
            print(f"✓ Created '{et}' trigger")
        except Exception as e:  # noqa: BLE001
            print(f"✗ Failed to create '{et}' trigger: {_http_detail(e)}")

    print(f"\nDone. Hook {hook_id} -> {destination_url}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Create/inspect a single project's Procore Submittals webhook pointing at the milehigh sandbox app.",
    )
    parser.add_argument("--project-id", type=int, default=DEFAULT_PROJECT_ID,
                        help=f"Procore project ID (default: {DEFAULT_PROJECT_ID} = PROJ. # 999)")
    parser.add_argument("--destination-url", default=DEFAULT_DESTINATION_URL,
                        help=f"Webhook destination URL (default: {DEFAULT_DESTINATION_URL})")
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE,
                        help=f"Webhook namespace (default: {DEFAULT_NAMESPACE})")
    parser.add_argument("--company-id", type=int, default=cfg.PROD_PROCORE_COMPANY_ID,
                        help="Procore company ID (default: PROD_PROCORE_COMPANY_ID)")
    parser.add_argument("--payload-version", default="v4.0",
                        help="Hook payload_version (default: v4.0)")
    parser.add_argument("--list", action="store_true", help="Only list existing hooks/triggers, make no changes")
    parser.add_argument("--delete", action="store_true", help="Delete existing hook(s) for the namespace, then stop")
    parser.add_argument("--dry-run", action="store_true", help="Report planned changes without mutating Procore")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        return run(
            project_id=args.project_id,
            destination_url=args.destination_url,
            namespace=args.namespace,
            company_id=args.company_id,
            payload_version=args.payload_version,
            do_list=args.list,
            do_delete=args.delete,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    raise SystemExit(main())
