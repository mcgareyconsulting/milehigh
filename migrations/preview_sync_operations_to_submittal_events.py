"""
Preview script to show how SyncOperation/SyncLog data would be converted
directly to SubmittalEvents format.

This approach ignores ProcoreWebhookEvents entirely and just uses the
actual operation logs that contain the real change data.

This script is READ-ONLY and does not modify the database.

Usage:
    python migrations/preview_sync_operations_to_submittal_events.py [--limit N] [--submittal-id ID]
"""

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

load_dotenv()

try:
    from app.models import (
        db, SyncOperation, SyncLog
    )
    from app import create_app
except ImportError as e:
    print(f"Error importing models: {e}")
    sys.exit(1)


def _create_submittal_payload_hash(action, submittal_id, payload):
    """Create a hash for the submittal event payload."""
    payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    hash_string = f"{action}:{submittal_id}:{payload_json}"
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
    elif 'created' in message_lower and 'submittal' in message_lower:
        return 'created'  # Special case for create events
    
    return None


def _determine_action_from_operation_type(operation_type):
    """Determine SubmittalEvents action from SyncOperation type."""
    if 'create' in operation_type.lower():
        return 'created'
    elif any(x in operation_type.lower() for x in ['ball', 'status', 'title', 'manager']):
        return 'updated'
    return 'updated'  # Default to updated


def find_procore_submittal_operations(limit=None, submittal_id_filter=None):
    """
    Find all SyncOperation records for Procore submittal changes.
    
    Operation types we're looking for:
    - procore_submittal_create
    - procore_ball_in_court
    - procore_submittal_status
    - procore_submittal_title
    - procore_submittal_manager
    """
    query = SyncOperation.query.filter(
        SyncOperation.source_system == 'procore'
    )
    
    # Filter by submittal_id if provided
    if submittal_id_filter:
        query = query.filter(SyncOperation.source_id == str(submittal_id_filter))
    
    # Only get procore submittal operations
    procore_ops = [
        'procore_submittal_create',
        'procore_ball_in_court',
        'procore_submittal_status',
        'procore_submittal_title',
        'procore_submittal_manager'
    ]
    query = query.filter(SyncOperation.operation_type.in_(procore_ops))
    
    # Order by most recent first
    query = query.order_by(SyncOperation.started_at.desc())
    
    if limit:
        query = query.limit(limit)
    
    return query.all()


def find_sync_logs_for_operation(operation):
    """Find SyncLog records for a SyncOperation."""
    logs = SyncLog.query.filter(
        SyncLog.operation_id == operation.operation_id
    ).order_by(SyncLog.timestamp).all()
    
    return logs


def build_payload_from_sync_logs(sync_logs, operation_type):
    """
    Build a SubmittalEvents payload from SyncLog entries.
    
    Args:
        sync_logs: List of SyncLog records
        operation_type: The SyncOperation type
    
    Returns:
        dict: Payload with field changes
    """
    payload = {}
    
    is_create = 'create' in operation_type.lower()
    
    if is_create:
        # For create events, collect initial values
        payload['migrated_from'] = 'SyncOperation + SyncLog'
        payload['migration_note'] = 'Created from sync operation logs'
        
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
    else:
        # For update events, build old/new value pairs
        payload['migrated_from'] = 'SyncOperation + SyncLog'
        payload['migration_note'] = 'Created from sync operation logs with field changes'
        
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


def group_operations_by_submittal_and_time(operations, time_window_seconds=5):
    """
    Group operations that happened close together for the same submittal.
    This helps combine multiple field changes into single SubmittalEvents.
    
    Returns:
        dict: {(submittal_id, time_bucket): [operations]}
    """
    grouped = defaultdict(list)
    
    for op in operations:
        submittal_id = op.source_id
        # Round to nearest time window to group close operations
        time_bucket = op.started_at.replace(
            second=(op.started_at.second // time_window_seconds) * time_window_seconds,
            microsecond=0
        )
        
        key = (submittal_id, time_bucket)
        grouped[key].append(op)
    
    return grouped


def preview_conversion(limit=10, submittal_id_filter=None, group_operations=True):
    """
    Preview how SyncOperation/SyncLog would be converted to SubmittalEvents.
    
    Args:
        limit: Maximum number of operations to preview
        submittal_id_filter: Optional submittal_id to filter by
        group_operations: If True, group operations by submittal and time
    """
    app = create_app()
    
    with app.app_context():
        # Find all procore submittal operations
        operations = find_procore_submittal_operations(
            limit=limit if not group_operations else None,
            submittal_id_filter=submittal_id_filter
        )
        
        if not operations:
            print("No Procore submittal SyncOperation records found.")
            return
        
        print("=" * 100)
        print("PREVIEW: SyncOperation/SyncLog → SubmittalEvents Conversion")
        print("=" * 100)
        print(f"\nFound {len(operations)} SyncOperation records\n")
        
        if group_operations:
            # Group operations by submittal and time
            grouped = group_operations_by_submittal_and_time(operations, time_window_seconds=5)
            print(f"Grouped into {len(grouped)} event groups (operations within 5 seconds)\n")
            print("=" * 100)
            
            # Process each group
            stats = {
                'total_groups': len(grouped),
                'total_operations': len(operations),
                'with_sync_data': 0,
                'without_sync_data': 0,
                'create_events': 0,
                'update_events': 0,
            }
            
            for idx, ((submittal_id, time_bucket), ops) in enumerate(grouped.items(), 1):
                print(f"\n{'='*100}")
                print(f"EVENT GROUP #{idx}: Submittal {submittal_id} at {time_bucket}")
                print(f"{'='*100}\n")
                
                print(f"📥 SOURCE DATA ({len(ops)} SyncOperation(s)):")
                for op in ops:
                    print(f"  - Operation ID: {op.operation_id}")
                    print(f"    Type: {op.operation_type}")
                    print(f"    Started: {op.started_at}")
                    print(f"    Source: {op.source_system} / {op.source_id}")
                
                # Collect all sync logs from all operations in this group
                all_sync_logs = []
                for op in ops:
                    logs = find_sync_logs_for_operation(op)
                    all_sync_logs.extend(logs)
                
                if all_sync_logs:
                    print(f"\n🔗 FOUND {len(all_sync_logs)} SyncLog entries:")
                    for log in all_sync_logs:
                        print(f"  • {log.message}")
                        if log.data:
                            if 'old_value' in log.data and 'new_value' in log.data:
                                print(f"    OLD: {log.data.get('old_value')}")
                                print(f"    NEW: {log.data.get('new_value')}")
                            elif 'submittal_title' in log.data:
                                print(f"    Title: {log.data.get('submittal_title')}")
                
                # Determine action from operation types
                # If any operation is a create, the action is 'created'
                # Otherwise, it's 'updated'
                has_create = any('create' in op.operation_type.lower() for op in ops)
                action = 'created' if has_create else 'updated'
                
                # Build payload from all logs
                # Use the first operation's type for payload building
                primary_op_type = ops[0].operation_type
                payload = build_payload_from_sync_logs(all_sync_logs, primary_op_type)
                
                if payload and all_sync_logs:
                    stats['with_sync_data'] += 1
                else:
                    stats['without_sync_data'] += 1
                
                # Create payload hash
                payload_hash = _create_submittal_payload_hash(action, submittal_id, payload)
                
                # Show target data
                print(f"\n📤 TARGET DATA (SubmittalEvents):")
                print(f"  - submittal_id: {submittal_id}")
                print(f"  - action: {action}")
                print(f"  - source: 'Procore'")
                print(f"  - user_id: None (migrated data)")
                print(f"  - created_at: {time_bucket}")
                print(f"  - applied_at: None (historical event)")
                
                print(f"\n📦 PAYLOAD:")
                print(json.dumps(payload, indent=2, default=str))
                
                print(f"\n🔐 PAYLOAD HASH:")
                print(f"  {payload_hash}")
                
                print(f"\n📋 FULL SubmittalEvent RECORD:")
                print(f"  {{")
                print(f"    'submittal_id': '{submittal_id}',")
                print(f"    'action': '{action}',")
                print(f"    'payload': {json.dumps(payload, indent=6, default=str)},")
                print(f"    'payload_hash': '{payload_hash}',")
                print(f"    'source': 'Procore',")
                print(f"    'user_id': None,")
                print(f"    'created_at': '{time_bucket}',")
                print(f"    'applied_at': None")
                print(f"  }}")
                
                if action == 'created':
                    stats['create_events'] += 1
                else:
                    stats['update_events'] += 1
        else:
            # Process each operation individually
            stats = {
                'total': len(operations),
                'with_sync_data': 0,
                'without_sync_data': 0,
                'create_events': 0,
                'update_events': 0,
            }
            
            for idx, op in enumerate(operations, 1):
                print(f"\n{'='*100}")
                print(f"OPERATION #{idx}: {op.operation_type} - Submittal {op.source_id}")
                print(f"{'='*100}\n")
                
                submittal_id = op.source_id
                action = _determine_action_from_operation_type(op.operation_type)
                
                print(f"📥 SOURCE DATA (SyncOperation):")
                print(f"  - operation_id: {op.operation_id}")
                print(f"  - operation_type: {op.operation_type}")
                print(f"  - source_system: {op.source_system}")
                print(f"  - source_id: {op.source_id}")
                print(f"  - started_at: {op.started_at}")
                
                # Get sync logs
                sync_logs = find_sync_logs_for_operation(op)
                
                if sync_logs:
                    print(f"\n🔗 FOUND {len(sync_logs)} SyncLog entries:")
                    for log in sync_logs:
                        print(f"  • {log.message}")
                        if log.data:
                            if 'old_value' in log.data and 'new_value' in log.data:
                                print(f"    OLD: {log.data.get('old_value')}")
                                print(f"    NEW: {log.data.get('new_value')}")
                
                # Build payload
                payload = build_payload_from_sync_logs(sync_logs, op.operation_type)
                
                if payload and sync_logs:
                    stats['with_sync_data'] += 1
                else:
                    stats['without_sync_data'] += 1
                
                # Create payload hash
                payload_hash = _create_submittal_payload_hash(action, submittal_id, payload)
                
                print(f"\n📤 TARGET DATA (SubmittalEvents):")
                print(f"  - submittal_id: {submittal_id}")
                print(f"  - action: {action}")
                print(f"  - source: 'Procore'")
                print(f"  - created_at: {op.started_at}")
                
                print(f"\n📦 PAYLOAD:")
                print(json.dumps(payload, indent=2, default=str))
                
                print(f"\n🔐 PAYLOAD HASH:")
                print(f"  {payload_hash}")
                
                if action == 'created':
                    stats['create_events'] += 1
                else:
                    stats['update_events'] += 1
        
        # Summary
        print(f"\n{'='*100}")
        print("SUMMARY")
        print(f"{'='*100}\n")
        if group_operations:
            print(f"Total operation groups: {stats['total_groups']}")
            print(f"Total operations: {stats['total_operations']}")
        else:
            print(f"Total operations: {stats['total']}")
        print(f"  - Create events: {stats['create_events']}")
        print(f"  - Update events: {stats['update_events']}")
        print(f"Events with SyncLog data: {stats['with_sync_data']}")
        print(f"Events without SyncLog data: {stats['without_sync_data']}")
        print()
        print("💡 NOTES:")
        print("  - This approach uses SyncOperation/SyncLog directly (ignores ProcoreWebhookEvents)")
        print("  - Operations are grouped by submittal_id and time window (5 seconds)")
        print("  - Multiple field changes within the time window become one SubmittalEvent")
        print("  - Payload hash is used for deduplication in the new system")
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Preview SyncOperation/SyncLog → SubmittalEvents conversion'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='Maximum number of operations to preview (default: 10)'
    )
    parser.add_argument(
        '--submittal-id',
        type=str,
        default=None,
        help='Filter by specific submittal_id'
    )
    parser.add_argument(
        '--no-group',
        action='store_true',
        help='Do not group operations (show each operation separately)'
    )
    
    args = parser.parse_args()
    
    try:
        preview_conversion(
            limit=args.limit,
            submittal_id_filter=args.submittal_id,
            group_operations=not args.no_group
        )
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

