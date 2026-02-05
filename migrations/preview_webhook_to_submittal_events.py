"""
Preview script to show how ProcoreWebhookEvents + SyncLog data
would be converted to SubmittalEvents format.

This script is READ-ONLY and does not modify the database.
It shows:
- Current ProcoreWebhookEvents data
- Related SyncOperation/SyncLog data
- How payloads would be built
- What the payload_hash would be
- Sample SubmittalEvents records

Usage:
    python migrations/preview_webhook_to_submittal_events.py [--limit N] [--submittal-id ID]
"""

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from dotenv import load_dotenv
from sqlalchemy import and_

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

load_dotenv()

try:
    from app.models import (
        db, ProcoreWebhookEvents, SyncOperation, SyncLog
    )
    from app import create_app
except ImportError as e:
    print(f"Error importing models: {e}")
    sys.exit(1)


def _create_submittal_payload_hash(action, submittal_id, payload):
    """
    Create a hash for the submittal event payload to prevent duplicates.
    This matches the function from excel_poller_teardown branch.
    """
    # Normalize the payload by sorting keys and converting to JSON
    payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    
    # Create hash string from action + submittal_id + payload
    hash_string = f"{action}:{submittal_id}:{payload_json}"
    
    # Generate SHA-256 hash
    return hashlib.sha256(hash_string.encode('utf-8')).hexdigest()


def _extract_field_name_from_message(message):
    """Extract field name from sync log message."""
    message_lower = message.lower()
    
    if 'ball in court' in message_lower:
        return 'ball_in_court'
    elif 'status' in message_lower and 'submittal' in message_lower:
        return 'status'
    elif 'title' in message_lower and 'submittal' in message_lower:
        return 'title'
    elif 'manager' in message_lower and 'submittal' in message_lower:
        return 'submittal_manager'
    
    return None


def find_related_sync_operations(webhook_event, time_window_seconds=10):
    """Find SyncOperation records related to a ProcoreWebhookEvent."""
    submittal_id = str(webhook_event.resource_id)
    event_time = webhook_event.last_seen
    
    time_start = event_time - timedelta(seconds=time_window_seconds)
    time_end = event_time + timedelta(seconds=time_window_seconds)
    
    operations = SyncOperation.query.filter(
        and_(
            SyncOperation.source_system == 'procore',
            SyncOperation.source_id == submittal_id,
            SyncOperation.started_at >= time_start,
            SyncOperation.started_at <= time_end
        )
    ).all()
    
    return operations


def find_sync_logs_for_operation(operation):
    """Find SyncLog records for a SyncOperation."""
    logs = SyncLog.query.filter(
        SyncLog.operation_id == operation.operation_id
    ).order_by(SyncLog.timestamp).all()
    
    return logs


def build_payload_from_sync_logs(sync_logs, event_type):
    """
    Build a SubmittalEvents payload from SyncLog entries.
    
    Returns:
        dict: Payload with field changes
    """
    payload = {}
    
    if event_type == 'create':
        payload['migrated_from'] = 'ProcoreWebhookEvents + SyncLog'
        payload['migration_note'] = 'Created from webhook event and sync logs'
        
        # Extract initial values from sync logs
        for log in sync_logs:
            if log.data:
                if 'submittal_id' in log.data:
                    payload['submittal_id'] = log.data['submittal_id']
                if 'project_id' in log.data:
                    payload['project_id'] = log.data['project_id']
                if 'submittal_title' in log.data:
                    payload['title'] = log.data['submittal_title']
                if 'project_name' in log.data:
                    payload['project_name'] = log.data['project_name']
                # For create, new_value is the initial value
                if 'new_value' in log.data:
                    field_name = _extract_field_name_from_message(log.message)
                    if field_name:
                        payload[field_name] = log.data['new_value']
    else:
        # For update events, build old/new value pairs
        payload['migrated_from'] = 'ProcoreWebhookEvents + SyncLog'
        payload['migration_note'] = 'Created from webhook event and sync logs with field changes'
        
        for log in sync_logs:
            if log.data and 'old_value' in log.data and 'new_value' in log.data:
                field_name = _extract_field_name_from_message(log.message)
                if field_name:
                    payload[field_name] = {
                        'old': log.data['old_value'],
                        'new': log.data['new_value']
                    }
            
            # Also capture metadata
            if log.data:
                if 'submittal_id' in log.data:
                    payload['submittal_id'] = log.data['submittal_id']
                if 'project_id' in log.data:
                    payload['project_id'] = log.data['project_id']
    
    return payload


def build_minimal_payload(webhook_event):
    """Build minimal payload when no SyncLog data is available."""
    return {
        'migrated_from': 'ProcoreWebhookEvents',
        'original_resource_id': webhook_event.resource_id,
        'original_project_id': webhook_event.project_id,
        'original_event_type': webhook_event.event_type,
        'migration_note': 'No SyncLog data found for this event. Minimal payload created.',
        'webhook_last_seen': webhook_event.last_seen.isoformat() if webhook_event.last_seen else None
    }


def preview_conversion(limit=10, submittal_id_filter=None):
    """
    Preview how ProcoreWebhookEvents would be converted to SubmittalEvents.
    
    Args:
        limit: Maximum number of events to preview
        submittal_id_filter: Optional submittal_id to filter by
    """
    app = create_app()
    
    with app.app_context():
        # Get webhook events
        query = ProcoreWebhookEvents.query.order_by(
            ProcoreWebhookEvents.last_seen.desc()
        )
        
        if submittal_id_filter:
            query = query.filter_by(resource_id=int(submittal_id_filter))
        
        webhook_events = query.limit(limit).all()
        
        if not webhook_events:
            print("No ProcoreWebhookEvents found.")
            return
        
        print("=" * 100)
        print("PREVIEW: ProcoreWebhookEvents → SubmittalEvents Conversion")
        print("=" * 100)
        print(f"\nFound {len(webhook_events)} webhook events to preview\n")
        
        # Group by (submittal_id, event_type) to show unique events
        events_by_key = {}
        for webhook_event in webhook_events:
            key = (str(webhook_event.resource_id), webhook_event.event_type)
            if key not in events_by_key or webhook_event.last_seen > events_by_key[key].last_seen:
                events_by_key[key] = webhook_event
        
        print(f"After deduplication: {len(events_by_key)} unique events\n")
        print("=" * 100)
        
        stats = {
            'total': len(events_by_key),
            'with_sync_data': 0,
            'without_sync_data': 0,
            'create_events': 0,
            'update_events': 0,
        }
        
        # Preview each event
        for idx, ((submittal_id, event_type), webhook_event) in enumerate(events_by_key.items(), 1):
            print(f"\n{'='*100}")
            print(f"EVENT #{idx}: Submittal {submittal_id} - {event_type.upper()}")
            print(f"{'='*100}\n")
            
            # Map event_type to action
            action_map = {'create': 'created', 'update': 'updated'}
            action = action_map.get(event_type, event_type)
            
            # Show source data
            print("📥 SOURCE DATA (ProcoreWebhookEvents):")
            print(f"  - resource_id (submittal_id): {webhook_event.resource_id}")
            print(f"  - project_id: {webhook_event.project_id}")
            print(f"  - event_type: {webhook_event.event_type}")
            print(f"  - last_seen: {webhook_event.last_seen}")
            print()
            
            # Try to find related SyncOperation/SyncLog data
            sync_operations = find_related_sync_operations(webhook_event, time_window_seconds=10)
            
            payload = {}
            has_sync_data = False
            sync_logs_found = []
            
            if sync_operations:
                print(f"🔗 FOUND {len(sync_operations)} related SyncOperation(s):")
                for op in sync_operations:
                    print(f"  - Operation ID: {op.operation_id}")
                    print(f"    Type: {op.operation_type}")
                    print(f"    Started: {op.started_at}")
                    print(f"    Source: {op.source_system} / {op.source_id}")
                    
                    logs = find_sync_logs_for_operation(op)
                    if logs:
                        sync_logs_found.extend(logs)
                        print(f"    └─ {len(logs)} SyncLog entries found")
                        for log in logs:
                            print(f"       • {log.message}")
                            if log.data:
                                if 'old_value' in log.data and 'new_value' in log.data:
                                    print(f"         OLD: {log.data.get('old_value')}")
                                    print(f"         NEW: {log.data.get('new_value')}")
                print()
                
                if sync_logs_found:
                    payload = build_payload_from_sync_logs(sync_logs_found, event_type)
                    has_sync_data = True
                    stats['with_sync_data'] += 1
            else:
                print("⚠️  No related SyncOperation found (searching ±10 seconds from last_seen)")
                print()
            
            if not payload or not has_sync_data:
                payload = build_minimal_payload(webhook_event)
                stats['without_sync_data'] += 1
                print("⚠️  Using minimal payload (no SyncLog data available)")
            
            # Create payload hash
            payload_hash = _create_submittal_payload_hash(action, submittal_id, payload)
            
            # Show what SubmittalEvent would look like
            print("📤 TARGET DATA (SubmittalEvents):")
            print(f"  - submittal_id: {submittal_id}")
            print(f"  - action: {action}")
            print(f"  - source: 'Procore'")
            print(f"  - user_id: None (migrated data)")
            print(f"  - created_at: {webhook_event.last_seen}")
            print(f"  - applied_at: None (historical event)")
            print()
            
            print("📦 PAYLOAD:")
            print(json.dumps(payload, indent=2, default=str))
            print()
            
            print("🔐 PAYLOAD HASH:")
            print(f"  {payload_hash}")
            print()
            
            print("📋 FULL SubmittalEvent RECORD:")
            print(f"  {{")
            print(f"    'submittal_id': '{submittal_id}',")
            print(f"    'action': '{action}',")
            print(f"    'payload': {json.dumps(payload, indent=6, default=str)},")
            print(f"    'payload_hash': '{payload_hash}',")
            print(f"    'source': 'Procore',")
            print(f"    'user_id': None,")
            print(f"    'created_at': '{webhook_event.last_seen}',")
            print(f"    'applied_at': None")
            print(f"  }}")
            
            if event_type == 'create':
                stats['create_events'] += 1
            else:
                stats['update_events'] += 1
            
            # Show separator (except for last item)
            if idx < len(events_by_key):
                print()
        
        # Summary
        print(f"\n{'='*100}")
        print("SUMMARY")
        print(f"{'='*100}\n")
        print(f"Total unique events: {stats['total']}")
        print(f"  - Create events: {stats['create_events']}")
        print(f"  - Update events: {stats['update_events']}")
        print(f"Events with SyncLog data: {stats['with_sync_data']}")
        print(f"Events without SyncLog data: {stats['without_sync_data']}")
        print()
        print("💡 NOTES:")
        print("  - Events with SyncLog data will have complete payloads with old/new values")
        print("  - Events without SyncLog data will have minimal payloads")
        print("  - Payload hash is used for deduplication in the new system")
        print("  - All migrated events will have source='Procore' and user_id=None")
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Preview ProcoreWebhookEvents → SubmittalEvents conversion'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='Maximum number of events to preview (default: 10)'
    )
    parser.add_argument(
        '--submittal-id',
        type=str,
        default=None,
        help='Filter by specific submittal_id'
    )
    
    args = parser.parse_args()
    
    try:
        preview_conversion(limit=args.limit, submittal_id_filter=args.submittal_id)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

