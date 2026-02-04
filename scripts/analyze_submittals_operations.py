#!/usr/bin/env python3
"""
Procore Submittals Operations Analysis Script

Analyzes submittal data to provide insights on:
- Average submittal lifespan (creation to closed)
- Average ball in court times
- Status distribution and transitions
- Project and type-level statistics
- Other operational metrics

Output: Markdown report (and optionally PDF)
"""

import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict
from statistics import mean, median, stdev
from typing import Dict, List, Tuple, Optional
import json

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db, ProcoreSubmittal, SyncOperation, SyncLog
from sqlalchemy import func, and_, or_


def format_timedelta(td: timedelta) -> str:
    """Format timedelta as human-readable string."""
    if td is None:
        return "N/A"
    
    total_seconds = int(td.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    
    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    
    if not parts:
        return f"{total_seconds} second{'s' if total_seconds != 1 else ''}"
    
    return ", ".join(parts)


def get_submittals_with_create_events() -> Dict:
    """Get dict mapping submittal IDs to their create event timestamps."""
    create_ops = SyncOperation.query.filter(
        SyncOperation.operation_type == 'procore_submittal_create'
    ).order_by(SyncOperation.started_at).all()
    
    submittal_create_times = {}
    for op in create_ops:
        if op.source_id:
            submittal_id = str(op.source_id)
            # Get the create event timestamp from the operation or logs
            create_timestamp = op.started_at
            
            # Try to get more precise timestamp from logs
            logs = SyncLog.query.filter(
                SyncLog.operation_id == op.operation_id
            ).order_by(SyncLog.timestamp).first()
            
            if logs:
                create_timestamp = logs.timestamp
            
            submittal_create_times[submittal_id] = create_timestamp
    
    return submittal_create_times


def calculate_submittal_lifespans() -> Dict:
    """Calculate average submittal lifespan from creation to closed status.
    
    Returns both 'all' (all closed submittals) and 'true_create' (only those with create events)
    lifespans for comparison.
    """
    print("Calculating submittal lifespans...")
    
    # Get submittals with explicit create events and their timestamps
    submittal_create_times = get_submittals_with_create_events()
    print(f"Found {len(submittal_create_times)} submittals with explicit create events")
    
    # Find all submittals that are currently closed
    closed_submittals = ProcoreSubmittal.query.filter(
        ProcoreSubmittal.status.ilike('%closed%')
    ).all()
    
    # Find when each submittal was closed by looking at SyncLog
    all_lifespans = []
    true_create_lifespans = []
    closed_dates = {}
    
    for submittal in closed_submittals:
        submittal_id = submittal.submittal_id
        has_create_event = submittal_id in submittal_create_times
        create_event_timestamp = submittal_create_times.get(submittal_id)
        
        # Find the status change operation that set status to closed
        status_ops = SyncOperation.query.filter(
            SyncOperation.operation_type == 'procore_submittal_status',
            SyncOperation.source_id == str(submittal_id)
        ).order_by(SyncOperation.started_at).all()
        
        closed_date = None
        for op in status_ops:
            # Get logs for this operation
            logs = SyncLog.query.filter(
                SyncLog.operation_id == op.operation_id,
                SyncLog.data.isnot(None)
            ).order_by(SyncLog.timestamp).all()
            
            for log in logs:
                if log.data and isinstance(log.data, dict):
                    new_value = log.data.get('new_value', '')
                    if new_value and 'closed' in str(new_value).lower():
                        closed_date = log.timestamp
                        break
            
            if closed_date:
                break
        
        # Determine the creation timestamp to use
        # For true create submittals, use the create event timestamp
        # For others, use the database created_at (which may be inaccurate for seeded submittals)
        if has_create_event and create_event_timestamp:
            creation_timestamp = create_event_timestamp
            use_create_event = True
        elif submittal.created_at:
            creation_timestamp = submittal.created_at
            use_create_event = False
        else:
            # Skip if no creation timestamp available
            continue
        
        # If we found a closed date, calculate lifespan
        if closed_date and creation_timestamp:
            lifespan = closed_date - creation_timestamp
            lifespan_days = lifespan.total_seconds() / 86400
            
            # Only include lifespans > 0 days (filter out submittals added with status closed)
            # Also filter out very small lifespans (< 0.1 days = 2.4 hours) which might be data issues
            if lifespan_days > 0.1:
                lifespan_data = {
                    'submittal_id': submittal_id,
                    'title': submittal.title,
                    'project_name': submittal.project_name,
                    'project_id': submittal.procore_project_id,
                    'created_at': creation_timestamp,
                    'closed_at': closed_date,
                    'lifespan_days': lifespan_days,
                    'lifespan': lifespan,
                    'has_create_event': has_create_event,
                    'used_create_event_timestamp': use_create_event
                }
                
                all_lifespans.append(lifespan_data)
                
                # Only include in true_create if it has a create event and we used the create timestamp
                if has_create_event and use_create_event:
                    true_create_lifespans.append(lifespan_data)
                
                closed_dates[submittal_id] = closed_date
    
    def calculate_stats(lifespan_list):
        """Helper to calculate statistics for a list of lifespans."""
        if not lifespan_list:
            return {
                'total_closed': 0,
                'average_days': 0,
                'median_days': 0,
                'min_days': 0,
                'max_days': 0,
                'stdev_days': 0,
                'details': []
            }
        
        lifespan_days = [l['lifespan_days'] for l in lifespan_list]
        return {
            'total_closed': len(lifespan_list),
            'average_days': mean(lifespan_days),
            'median_days': median(lifespan_days),
            'min_days': min(lifespan_days),
            'max_days': max(lifespan_days),
            'stdev_days': stdev(lifespan_days) if len(lifespan_days) > 1 else 0,
            'details': lifespan_list
        }
    
    # Calculate statistics for both sets
    total_closed_submittals = len(closed_submittals)
    filtered_out_zero = total_closed_submittals - len(all_lifespans)
    filtered_out_no_create = len(all_lifespans) - len(true_create_lifespans)
    
    all_stats = calculate_stats(all_lifespans)
    true_create_stats = calculate_stats(true_create_lifespans)
    
    return {
        'all': {
            **all_stats,
            'total_closed_before_filter': total_closed_submittals,
            'filtered_out_zero_days': filtered_out_zero,
            'closed_dates': closed_dates
        },
        'true_create': {
            **true_create_stats,
            'filtered_out_no_create_event': filtered_out_no_create,
            'closed_dates': closed_dates
        },
        'summary': {
            'total_closed_submittals': total_closed_submittals,
            'with_create_events': len(submittal_create_times),
            'all_after_filters': len(all_lifespans),
            'true_create_after_filters': len(true_create_lifespans)
        }
    }


def calculate_project_lifespan_statistics(lifespans_data: List[Dict]) -> Dict:
    """Calculate average submittal lifespan by project."""
    print("Calculating project-level lifespan statistics...")
    
    # Group lifespans by project
    project_lifespans = defaultdict(list)
    
    for lifespan in lifespans_data:
        project_name = lifespan.get('project_name') or 'Unknown Project'
        project_id = lifespan.get('project_id') or 'Unknown'
        project_key = f"{project_name} ({project_id})"
        project_lifespans[project_key].append(lifespan['lifespan_days'])
    
    # Calculate statistics per project
    project_stats = []
    for project_key, days_list in project_lifespans.items():
        if days_list:
            project_stats.append({
                'project_name': project_key,
                'count': len(days_list),
                'average_days': mean(days_list),
                'median_days': median(days_list),
                'min_days': min(days_list),
                'max_days': max(days_list),
                'stdev_days': stdev(days_list) if len(days_list) > 1 else 0
            })
    
    # Sort by average days (descending)
    project_stats.sort(key=lambda x: x['average_days'], reverse=True)
    
    return {
        'by_project': project_stats,
        'total_projects_with_closed': len(project_stats)
    }


def find_natural_cutoff(durations: List[float]) -> tuple:
    """Find a natural cutoff point by analyzing duration distribution.
    
    Looks for a gap/jump in the data where noise (very short periods) ends
    and real periods begin. For example, if there are 105 records at a few seconds
    then suddenly one at 4 minutes, that 4 minutes should be the cutoff.
    
    Returns:
        tuple: (cutoff_days, explanation_dict) where explanation_dict contains
        details about how the cutoff was determined
    """
    if not durations or len(durations) < 5:
        # Very small dataset - use 1 minute as conservative default
        default_cutoff = 0.0007  # ~1 minute
        return default_cutoff, {
            'method': 'default_insufficient_data',
            'cutoff_days': default_cutoff,
            'cutoff_hours': default_cutoff * 24,
            'cutoff_minutes': default_cutoff * 24 * 60,
            'reason': 'Insufficient data for analysis, using 1 minute default'
        }
    
    sorted_durations = sorted(durations)
    total_count = len(sorted_durations)
    
    # Convert to minutes for easier analysis
    sorted_minutes = [d * 24 * 60 for d in sorted_durations]
    
    # Strategy: Look for inflection points - significant jumps in the distribution
    # Example: many periods at 1.25 minutes, then jump to 3 minutes = inflection point
    # Focus on finding where there's a clear break in the distribution
    
    # Analyze first 40% of data (where noise and short periods likely cluster)
    analysis_window = max(50, int(total_count * 0.40))
    analysis_window = min(analysis_window, len(sorted_minutes) - 1)
    
    # Look for the most significant gap/inflection point
    max_gap = 0
    max_gap_index = -1
    max_gap_score = 0
    
    for i in range(analysis_window):
        if sorted_minutes[i] > 0:
            gap = sorted_minutes[i + 1] - sorted_minutes[i]
            current_value = sorted_minutes[i]
            next_value = sorted_minutes[i + 1]
            
            # Calculate relative gap (gap as multiple of current value)
            if current_value > 0:
                relative_gap = gap / current_value
            else:
                relative_gap = gap
            
            # Score based on how significant the jump is
            gap_score = 0
            
            # Very high score for large relative jumps (2x, 3x+)
            if relative_gap > 2.5:  # 2.5x jump (e.g., 1.25 → 3.125)
                gap_score += 15
            elif relative_gap > 2.0:  # 2x jump (e.g., 1.5 → 3.0)
                gap_score += 10
            elif relative_gap > 1.5:  # 1.5x jump
                gap_score += 5
            
            # Bonus for absolute gap size
            if gap > 1.5:  # 1.5+ minute gap
                gap_score += 8
            elif gap > 1.0:  # 1+ minute gap
                gap_score += 5
            elif gap > 0.5:  # 30+ second gap
                gap_score += 2
            
            # Extra bonus for gaps in the 1-5 minute range (where inflection points often are)
            if 0.5 <= current_value <= 5.0:
                gap_score += 5
                # Even more bonus if next value is in a higher range
                if next_value > 2.0:
                    gap_score += 3
            
            # Prefer gaps that separate clusters (low values from higher values)
            if current_value < 2.0 and next_value >= 2.0:
                gap_score += 5  # Separating < 2 min from >= 2 min
            
            # Consider any gap that's meaningful
            if gap > 0.2 and relative_gap > 1.1:  # At least 12 seconds and 10% relative jump
                if gap_score > max_gap_score:
                    max_gap = gap
                    max_gap_index = i + 1
                    max_gap_score = gap_score
    
    # If we found a significant inflection point, use the value after the gap as cutoff
    cutoff_minutes = None
    gap_info = None
    if max_gap_index > 0 and max_gap_score > 5:  # Gap must have a meaningful score
        cutoff_minutes = sorted_minutes[max_gap_index]
        value_before = sorted_minutes[max_gap_index - 1]
        cutoff_days = cutoff_minutes / (24 * 60)
        method = 'inflection_point_detection'
        relative_jump = (cutoff_minutes / value_before) if value_before > 0 else 0
        reason = f'Found inflection point: jump from {value_before:.2f} to {cutoff_minutes:.2f} minutes (gap: {max_gap:.2f} min, {relative_jump:.2f}x jump, score: {max_gap_score:.1f}) at index {max_gap_index}'
        
        # Store gap info for reporting
        gap_info = {
            'gap_minutes': max_gap,
            'gap_index': max_gap_index,
            'value_before_gap_minutes': value_before,
            'value_after_gap_minutes': cutoff_minutes,
            'relative_jump': relative_jump,
            'gap_score': max_gap_score
        }
    else:
        # No clear gap found - look for percentile-based breakpoints
        # Calculate percentiles in minutes
        percentiles_minutes = {
            '1st': sorted_minutes[max(0, int(total_count * 0.01))],
            '2nd': sorted_minutes[max(0, int(total_count * 0.02))],
            '5th': sorted_minutes[max(0, int(total_count * 0.05))],
            '10th': sorted_minutes[max(0, int(total_count * 0.10))],
        }
        
        # Look for jumps between percentiles
        p1_to_p2 = percentiles_minutes['2nd'] - percentiles_minutes['1st']
        p2_to_p5 = percentiles_minutes['5th'] - percentiles_minutes['2nd']
        p5_to_p10 = percentiles_minutes['10th'] - percentiles_minutes['5th']
        
        # Find the largest relative jump - look for inflection points
        # Check if percentiles show clear jumps indicating inflection points
        p5_in_range = 1.0 <= percentiles_minutes['5th'] <= 5.0
        p10_in_range = 1.0 <= percentiles_minutes['10th'] <= 5.0
        
        # Calculate relative jumps
        p1_to_p2_relative = (p1_to_p2 / percentiles_minutes['1st']) if percentiles_minutes['1st'] > 0 else 0
        p2_to_p5_relative = (p2_to_p5 / percentiles_minutes['2nd']) if percentiles_minutes['2nd'] > 0 else 0
        p5_to_p10_relative = (p5_to_p10 / percentiles_minutes['5th']) if percentiles_minutes['5th'] > 0 else 0
        
        # Look for significant relative jumps (inflection points)
        if p2_to_p5_relative > 1.5 and p2_to_p5 > 0.3:  # 1.5x jump and at least 18 seconds
            cutoff_minutes = percentiles_minutes['5th']
            method = 'percentile_inflection_5th'
            reason = f'Inflection point detected: 2nd to 5th percentile jump of {p2_to_p5:.2f} minutes ({p2_to_p5_relative:.2f}x relative). Cutoff: {cutoff_minutes:.2f} minutes'
        elif p5_to_p10_relative > 1.3 and p5_to_p10 > 0.3:
            cutoff_minutes = percentiles_minutes['10th']
            method = 'percentile_inflection_10th'
            reason = f'Inflection point detected: 5th to 10th percentile jump of {p5_to_p10:.2f} minutes ({p5_to_p10_relative:.2f}x relative). Cutoff: {cutoff_minutes:.2f} minutes'
        elif p1_to_p2_relative > 1.5 and p1_to_p2 > 0.3:
            cutoff_minutes = percentiles_minutes['2nd']
            method = 'percentile_inflection_2nd'
            reason = f'Inflection point detected: 1st to 2nd percentile jump of {p1_to_p2:.2f} minutes ({p1_to_p2_relative:.2f}x relative). Cutoff: {cutoff_minutes:.2f} minutes'
        else:
            # Look for clustering patterns - find where density changes
            # Check for first value that's significantly higher than many previous values
            if len(sorted_minutes) > 20:
                # Look at first 20 values, find first that's 2x+ the median of first 10
                first_10_median = median(sorted_minutes[:10])
                for i in range(10, min(30, len(sorted_minutes))):
                    if sorted_minutes[i] > first_10_median * 2.0 and sorted_minutes[i] > 1.0:
                        cutoff_minutes = sorted_minutes[i]
                        method = 'density_change_detection'
                        reason = f'Found density change: value {cutoff_minutes:.2f} minutes is {cutoff_minutes/first_10_median:.2f}x the median of first 10 values ({first_10_median:.2f} min)'
                        break
                
                if cutoff_minutes is None:
                    # Fallback to 5th percentile
                    cutoff_minutes = percentiles_minutes['5th']
                    method = 'percentile_5th_fallback'
                    reason = f'No clear inflection point detected. Using 5th percentile as cutoff: {cutoff_minutes:.2f} minutes'
            else:
                cutoff_minutes = percentiles_minutes['5th']
                method = 'percentile_5th_fallback'
                reason = f'Insufficient data for inflection detection. Using 5th percentile: {cutoff_minutes:.2f} minutes'
        
        cutoff_days = cutoff_minutes / (24 * 60)
    
    # Hard cutoff at 2.5 minutes - periods below this are considered noise
    original_cutoff_minutes = cutoff_minutes
    if cutoff_minutes < 2.5:
        cutoff_minutes = 2.5
        cutoff_days = cutoff_minutes / (24 * 60)
        if 'inflection' not in method and 'density' not in method:
            method = 'adjusted_to_2_5_minutes'
            reason = f'Cutoff set to hard minimum of 2.5 minutes (data-driven cutoff was {original_cutoff_minutes:.2f} minutes)'
        else:
            # Update reason to note the hard cutoff was applied
            reason += f' (adjusted to hard minimum of 2.5 minutes)'
    
    # Round to reasonable precision
    cutoff_days = round(cutoff_days, 6)  # Keep precision for minutes calculation
    cutoff_hours = cutoff_minutes / 60  # Calculate from minutes for accuracy
    # cutoff_minutes is already in minutes, no need to recalculate
    
    # Build explanation with available data
    explanation = {
        'method': method,
        'cutoff_days': cutoff_days,
        'cutoff_hours': cutoff_hours,
        'cutoff_minutes': cutoff_minutes,
        'reason': reason
    }
    
    # Add percentile data if we calculated it
    if 'percentiles_minutes' in locals():
        explanation['percentiles_minutes'] = {
            '1st': percentiles_minutes.get('1st', 0),
            '2nd': percentiles_minutes.get('2nd', 0),
            '5th': percentiles_minutes.get('5th', 0),
            '10th': percentiles_minutes.get('10th', 0),
        }
        explanation['jumps_minutes'] = {
            'p1_to_p2': p1_to_p2 if 'p1_to_p2' in locals() else 0,
            'p2_to_p5': p2_to_p5 if 'p2_to_p5' in locals() else 0,
            'p5_to_p10': p5_to_p10 if 'p5_to_p10' in locals() else 0,
        }
    
    # Add gap/inflection point information if we found one
    if gap_info:
        explanation['gap_detected'] = gap_info
    elif max_gap_index > 0:
        explanation['gap_detected'] = {
            'gap_minutes': max_gap,
            'gap_index': max_gap_index,
            'value_before_gap_minutes': sorted_minutes[max_gap_index - 1] if max_gap_index > 0 else 0,
            'value_after_gap_minutes': sorted_minutes[max_gap_index],
            'gap_score': max_gap_score
        }
    
    return cutoff_days, explanation


def bucket_duration(duration_days: float) -> str:
    """Bucket a duration into time ranges."""
    if duration_days < 1:
        return "< 1 day"
    elif duration_days < 3:
        return "1-3 days"
    elif duration_days < 5:
        return "3-5 days"
    elif duration_days < 7:
        return "5-7 days"
    elif duration_days < 14:
        return "1-2 weeks"
    elif duration_days < 21:
        return "2-3 weeks"
    elif duration_days < 30:
        return "3-4 weeks"
    elif duration_days < 60:
        return "1-2 months"
    elif duration_days < 90:
        return "2-3 months"
    else:
        return "> 3 months"


def calculate_ball_in_court_times() -> Dict:
    """Calculate average ball in court times for each assignee."""
    print("Calculating ball in court times...")
    
    # Get all ball in court change operations
    ball_ops = SyncOperation.query.filter(
        SyncOperation.operation_type == 'procore_ball_in_court'
    ).order_by(SyncOperation.started_at).all()
    
    # Track ball in court periods for each submittal
    submittal_periods = defaultdict(list)  # submittal_id -> list of (assignee, start_time, end_time)
    current_assignees = {}  # submittal_id -> (assignee, start_time)
    
    for op in ball_ops:
        submittal_id = op.source_id
        
        # Get logs for this operation
        logs = SyncLog.query.filter(
            SyncLog.operation_id == op.operation_id,
            SyncLog.data.isnot(None)
        ).order_by(SyncLog.timestamp).all()
        
        for log in logs:
            if log.data and isinstance(log.data, dict):
                old_value = log.data.get('old_value')
                new_value = log.data.get('new_value')
                timestamp = log.timestamp
                
                # End previous assignee's period
                if submittal_id in current_assignees:
                    prev_assignee, prev_start = current_assignees[submittal_id]
                    if prev_assignee and prev_assignee != new_value:
                        duration = timestamp - prev_start
                        if duration.total_seconds() > 0:
                            submittal_periods[submittal_id].append({
                                'assignee': prev_assignee,
                                'start': prev_start,
                                'end': timestamp,
                                'duration_days': duration.total_seconds() / 86400,
                                'duration': duration
                            })
                
                # Start new assignee's period
                if new_value:
                    current_assignees[submittal_id] = (new_value, timestamp)
                else:
                    # Ball cleared
                    if submittal_id in current_assignees:
                        del current_assignees[submittal_id]
    
    # Handle current (ongoing) assignments
    now = datetime.utcnow()
    for submittal_id, (assignee, start_time) in current_assignees.items():
        duration = now - start_time
        if duration.total_seconds() > 0:
            submittal_periods[submittal_id].append({
                'assignee': assignee,
                'start': start_time,
                'end': now,
                'duration_days': duration.total_seconds() / 86400,
                'duration': duration,
                'ongoing': True
            })
    
    # Collect all durations to find cutoff
    all_durations_raw = []
    for submittal_id, periods in submittal_periods.items():
        for period in periods:
            assignee = period['assignee']
            if assignee:  # Skip None/empty assignees
                all_durations_raw.append(period['duration_days'])
    
    # Find natural cutoff
    cutoff_days, cutoff_explanation = find_natural_cutoff(all_durations_raw)
    print(f"Found natural cutoff: {cutoff_days:.4f} days ({cutoff_explanation['cutoff_hours']:.2f} hours, {cutoff_explanation['cutoff_minutes']:.1f} minutes)")
    print(f"Cutoff method: {cutoff_explanation['method']}")
    print(f"Reason: {cutoff_explanation['reason']}")
    
    # Filter periods by cutoff and track filtered out periods
    filtered_periods = []
    filtered_out_periods = []
    for submittal_id, periods in submittal_periods.items():
        for period in periods:
            assignee = period['assignee']
            if assignee:
                if period['duration_days'] >= cutoff_days:
                    filtered_periods.append(period)
                else:
                    filtered_out_periods.append(period)
    
    filtered_out_count = len(filtered_out_periods)
    print(f"Filtered out {filtered_out_count} periods below {cutoff_explanation['cutoff_minutes']:.1f} minutes ({cutoff_explanation['cutoff_hours']:.2f} hours)")
    print(f"Retained {len(filtered_periods)} periods after filtering")
    
    # Analyze filtered out periods
    filtered_out_stats = {}
    if filtered_out_periods:
        filtered_durations = [p['duration_days'] * 24 * 60 for p in filtered_out_periods]  # Convert to minutes
        filtered_out_stats = {
            'count': len(filtered_out_periods),
            'min_minutes': min(filtered_durations),
            'max_minutes': max(filtered_durations),
            'avg_minutes': mean(filtered_durations),
            'median_minutes': median(filtered_durations),
            'distribution': defaultdict(int)
        }
        
        # Bucket the filtered out periods
        for duration_minutes in filtered_durations:
            if duration_minutes < 1:
                filtered_out_stats['distribution']['< 1 minute'] += 1
            elif duration_minutes < 5:
                filtered_out_stats['distribution']['1-5 minutes'] += 1
            elif duration_minutes < 10:
                filtered_out_stats['distribution']['5-10 minutes'] += 1
            elif duration_minutes < 15:
                filtered_out_stats['distribution']['10-15 minutes'] += 1
            elif duration_minutes < 30:
                filtered_out_stats['distribution']['15-30 minutes'] += 1
            else:
                filtered_out_stats['distribution']['30+ minutes'] += 1
        
        # Convert defaultdict to regular dict
        filtered_out_stats['distribution'] = dict(filtered_out_stats['distribution'])
    
    # Aggregate by assignee (using filtered periods)
    assignee_stats = defaultdict(list)
    assignee_buckets = defaultdict(lambda: defaultdict(int))  # assignee -> bucket -> count
    
    for period in filtered_periods:
        assignee = period['assignee']
        duration_days = period['duration_days']
        assignee_stats[assignee].append(duration_days)
        bucket = bucket_duration(duration_days)
        assignee_buckets[assignee][bucket] += 1
    
    # Calculate statistics per assignee
    assignee_analytics = {}
    for assignee, durations in assignee_stats.items():
        buckets = assignee_buckets[assignee]
        assignee_analytics[assignee] = {
            'total_periods': len(durations),
            'average_days': mean(durations),
            'median_days': median(durations),
            'min_days': min(durations),
            'max_days': max(durations),
            'total_days': sum(durations),
            'stdev_days': stdev(durations) if len(durations) > 1 else 0,
            'buckets': dict(buckets)
        }
    
    # Overall statistics (using filtered periods)
    all_durations = [p['duration_days'] for p in filtered_periods]
    overall_stats = {}
    overall_buckets = defaultdict(int)
    
    if all_durations:
        for duration in all_durations:
            bucket = bucket_duration(duration)
            overall_buckets[bucket] += 1
        
        overall_stats = {
            'total_periods': len(all_durations),
            'average_days': mean(all_durations),
            'median_days': median(all_durations),
            'min_days': min(all_durations),
            'max_days': max(all_durations),
            'stdev_days': stdev(all_durations) if len(all_durations) > 1 else 0,
            'buckets': dict(overall_buckets),
            'cutoff_days': cutoff_days,
            'cutoff_explanation': cutoff_explanation,
            'filtered_out_count': filtered_out_count,
            'filtered_out_stats': filtered_out_stats,
            'total_before_filter': len(all_durations_raw)
        }
    
    return {
        'overall': overall_stats,
        'by_assignee': assignee_analytics,
        'submittal_periods': dict(submittal_periods)
    }


def calculate_status_statistics() -> Dict:
    """Calculate statistics about submittal statuses."""
    print("Calculating status statistics...")
    
    # Current status distribution
    status_counts = db.session.query(
        ProcoreSubmittal.status,
        func.count(ProcoreSubmittal.id).label('count')
    ).group_by(ProcoreSubmittal.status).all()
    
    status_dist = {status: count for status, count in status_counts if status}
    
    # Status transitions (from SyncLog)
    transitions = defaultdict(int)
    status_ops = SyncOperation.query.filter(
        SyncOperation.operation_type == 'procore_submittal_status'
    ).all()
    
    for op in status_ops:
        logs = SyncLog.query.filter(
            SyncLog.operation_id == op.operation_id,
            SyncLog.data.isnot(None)
        ).all()
        
        for log in logs:
            if log.data and isinstance(log.data, dict):
                old_value = log.data.get('old_value')
                new_value = log.data.get('new_value')
                if old_value and new_value:
                    transition = f"{old_value} → {new_value}"
                    transitions[transition] += 1
    
    return {
        'current_distribution': status_dist,
        'transitions': dict(transitions),
        'total_submittals': sum(status_dist.values())
    }


def calculate_project_statistics() -> Dict:
    """Calculate statistics by project."""
    print("Calculating project statistics...")
    
    project_stats = db.session.query(
        ProcoreSubmittal.project_name,
        ProcoreSubmittal.procore_project_id,
        func.count(ProcoreSubmittal.id).label('total'),
        func.count(func.distinct(ProcoreSubmittal.status)).label('statuses'),
        func.count(func.distinct(ProcoreSubmittal.ball_in_court)).label('assignees')
    ).group_by(
        ProcoreSubmittal.project_name,
        ProcoreSubmittal.procore_project_id
    ).all()
    
    projects = []
    for project_name, project_id, total, statuses, assignees in project_stats:
        projects.append({
            'project_name': project_name,
            'project_id': project_id,
            'total_submittals': total,
            'unique_statuses': statuses,
            'unique_assignees': assignees
        })
    
    return {
        'projects': sorted(projects, key=lambda x: x['total_submittals'], reverse=True),
        'total_projects': len(projects)
    }


def calculate_type_statistics() -> Dict:
    """Calculate statistics by submittal type."""
    print("Calculating type statistics...")
    
    type_stats = db.session.query(
        ProcoreSubmittal.type,
        func.count(ProcoreSubmittal.id).label('count')
    ).group_by(ProcoreSubmittal.type).all()
    
    return {
        'distribution': {sub_type: count for sub_type, count in type_stats if sub_type},
        'total': sum(count for _, count in type_stats if _)
    }


def calculate_additional_metrics() -> Dict:
    """Calculate additional useful metrics."""
    print("Calculating additional metrics...")
    
    total_submittals = ProcoreSubmittal.query.count()
    
    # Submittals by creation date (recent activity)
    recent_submittals = ProcoreSubmittal.query.filter(
        ProcoreSubmittal.created_at >= datetime.utcnow() - timedelta(days=30)
    ).count()
    
    # Submittals updated recently
    recently_updated = ProcoreSubmittal.query.filter(
        ProcoreSubmittal.last_updated >= datetime.utcnow() - timedelta(days=7)
    ).count()
    
    # Average time since creation for open submittals
    open_submittals = ProcoreSubmittal.query.filter(
        ~ProcoreSubmittal.status.ilike('%closed%')
    ).all()
    
    open_ages = []
    for sub in open_submittals:
        if sub.created_at:
            age = (datetime.utcnow() - sub.created_at).total_seconds() / 86400
            open_ages.append(age)
    
    avg_open_age = mean(open_ages) if open_ages else 0
    
    # Ball in court distribution
    ball_dist = db.session.query(
        ProcoreSubmittal.ball_in_court,
        func.count(ProcoreSubmittal.id).label('count')
    ).group_by(ProcoreSubmittal.ball_in_court).all()
    
    return {
        'total_submittals': total_submittals,
        'recent_submittals_30d': recent_submittals,
        'recently_updated_7d': recently_updated,
        'open_submittals_count': len(open_ages),
        'average_open_age_days': avg_open_age,
        'ball_in_court_distribution': {ball: count for ball, count in ball_dist if ball}
    }


def generate_markdown_report(
    lifespans: Dict,
    ball_times: Dict,
    status_stats: Dict,
    project_stats: Dict,
    type_stats: Dict,
    additional_metrics: Dict,
    all_project_lifespan_stats: Dict,
    true_create_project_lifespan_stats: Dict
) -> str:
    """Generate markdown report from analysis data."""
    
    report = []
    report.append("# Procore Submittals Operations Analysis Report")
    report.append(f"\n**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
    report.append("---\n")
    
    # Executive Summary
    report.append("## Executive Summary\n")
    report.append(f"- **Total Submittals:** {additional_metrics['total_submittals']}")
    report.append(f"- **True Create-Closed Submittals:** {lifespans.get('true_create', {}).get('total_closed', 0)}")
    report.append(f"- **All Closed Submittals:** {lifespans.get('all', {}).get('total_closed', 0)}")
    report.append(f"- **Open Submittals:** {additional_metrics['open_submittals_count']}")
    report.append(f"- **Total Projects:** {project_stats['total_projects']}")
    report.append(f"- **Recent Activity (30 days):** {additional_metrics['recent_submittals_30d']} new submittals")
    report.append(f"- **Recent Updates (7 days):** {additional_metrics['recently_updated_7d']} submittals updated\n")
    
    # Submittal Lifespan Analysis
    report.append("## 1. Submittal Lifespan Analysis\n")
    
    # Summary of data sets
    summary = lifespans.get('summary', {})
    report.append("### Data Set Summary\n")
    report.append(f"- **Total Closed Submittals:** {summary.get('total_closed_submittals', 0)}")
    report.append(f"- **Submittals with Create Events:** {summary.get('with_create_events', 0)}")
    report.append(f"- **All Closed (after filters):** {summary.get('all_after_filters', 0)}")
    report.append(f"- **True Create-Closed (after filters):** {summary.get('true_create_after_filters', 0)}")
    report.append("")
    
    # True Create-Closed Analysis (Primary)
    true_create = lifespans.get('true_create', {})
    report.append("### True Create → Closed Lifespan Analysis ⭐\n")
    report.append("*This analysis only includes submittals with explicit create events, providing accurate end-to-end lifespans.*\n")
    
    if true_create.get('total_closed', 0) > 0:
        report.append(f"- **Total Closed Submittals Analyzed:** {true_create['total_closed']}")
        if true_create.get('filtered_out_no_create_event', 0) > 0:
            report.append(f"- **Submittals Excluded (no create event):** {true_create['filtered_out_no_create_event']}")
        report.append(f"- **Average Lifespan:** {true_create['average_days']:.2f} days ({format_timedelta(timedelta(days=true_create['average_days']))})")
        report.append(f"- **Median Lifespan:** {true_create['median_days']:.2f} days ({format_timedelta(timedelta(days=true_create['median_days']))})")
        report.append(f"- **Minimum Lifespan:** {true_create['min_days']:.2f} days ({format_timedelta(timedelta(days=true_create['min_days']))})")
        report.append(f"- **Maximum Lifespan:** {true_create['max_days']:.2f} days ({format_timedelta(timedelta(days=true_create['max_days']))})")
        report.append(f"- **Standard Deviation:** {true_create['stdev_days']:.2f} days\n")
        
        # Project-level lifespan statistics for true create
        if true_create_project_lifespan_stats and true_create_project_lifespan_stats.get('by_project'):
            report.append("#### Average Lifespan by Project (True Create-Closed)\n")
            report.append("| Project Name | Closed Submittals | Avg Lifespan (days) | Median (days) | Min (days) | Max (days) |")
            report.append("|-------------|-------------------|---------------------|--------------|------------|------------|")
            
            for project in true_create_project_lifespan_stats['by_project']:
                report.append(
                    f"| {project['project_name'][:50]} | {project['count']} | "
                    f"{project['average_days']:.2f} | {project['median_days']:.2f} | "
                    f"{project['min_days']:.2f} | {project['max_days']:.2f} |"
                )
            report.append("")
        
        # Top 10 longest/shortest for true create
        sorted_true_create = sorted(true_create['details'], key=lambda x: x['lifespan_days'], reverse=True)
        report.append("#### Longest Lifespans - True Create (Top 10)\n")
        report.append("| Submittal ID | Title | Project | Lifespan |")
        report.append("|--------------|-------|---------|----------|")
        for item in sorted_true_create[:10]:
            title = (item['title'] or 'N/A')[:50]
            project = (item['project_name'] or 'N/A')[:30]
            report.append(f"| {item['submittal_id']} | {title} | {project} | {item['lifespan_days']:.1f} days |")
        report.append("")
        
        report.append("#### Shortest Lifespans - True Create (Top 10)\n")
        report.append("| Submittal ID | Title | Project | Lifespan |")
        report.append("|--------------|-------|---------|----------|")
        for item in sorted_true_create[-10:]:
            title = (item['title'] or 'N/A')[:50]
            project = (item['project_name'] or 'N/A')[:30]
            report.append(f"| {item['submittal_id']} | {title} | {project} | {item['lifespan_days']:.1f} days |")
        report.append("")
    else:
        report.append("No true create-closed submittals found.\n")
    
    # All Closed Analysis (Reference)
    all_data = lifespans.get('all', {})
    report.append("### All Closed Submittals Analysis (Reference)\n")
    report.append("*This includes all closed submittals, including those seeded mid-lifespan. Use for reference only.*\n")
    
    if all_data.get('total_closed', 0) > 0:
        report.append(f"- **Total Closed Submittals Analyzed:** {all_data['total_closed']}")
        if all_data.get('filtered_out_zero_days', 0) > 0:
            report.append(f"- **Submittals Filtered Out (0-day lifespan):** {all_data['filtered_out_zero_days']}")
            report.append(f"- **Total Closed Submittals (before filter):** {all_data.get('total_closed_before_filter', all_data['total_closed'])}")
        report.append(f"- **Average Lifespan:** {all_data['average_days']:.2f} days ({format_timedelta(timedelta(days=all_data['average_days']))})")
        report.append(f"- **Median Lifespan:** {all_data['median_days']:.2f} days ({format_timedelta(timedelta(days=all_data['median_days']))})")
        report.append(f"- **Minimum Lifespan:** {all_data['min_days']:.2f} days ({format_timedelta(timedelta(days=all_data['min_days']))})")
        report.append(f"- **Maximum Lifespan:** {all_data['max_days']:.2f} days ({format_timedelta(timedelta(days=all_data['max_days']))})")
        report.append(f"- **Standard Deviation:** {all_data['stdev_days']:.2f} days\n")
        
        # Project-level lifespan statistics for all
        if all_project_lifespan_stats and all_project_lifespan_stats.get('by_project'):
            report.append("#### Average Lifespan by Project (All Closed)\n")
            report.append("| Project Name | Closed Submittals | Avg Lifespan (days) | Median (days) | Min (days) | Max (days) |")
            report.append("|-------------|-------------------|---------------------|--------------|------------|------------|")
            
            for project in all_project_lifespan_stats['by_project']:
                report.append(
                    f"| {project['project_name'][:50]} | {project['count']} | "
                    f"{project['average_days']:.2f} | {project['median_days']:.2f} | "
                    f"{project['min_days']:.2f} | {project['max_days']:.2f} |"
                )
            report.append("")
    else:
        report.append("No closed submittals found in the database.\n")
    
    # Ball in Court Analysis
    report.append("## 2. Ball in Court Time Analysis\n")
    
    if ball_times['overall']:
        overall = ball_times['overall']
        report.append("### Overall Statistics\n")
        report.append(f"- **Total Periods Tracked (after filter):** {overall['total_periods']}")
        if overall.get('total_before_filter'):
            report.append(f"- **Total Periods (before filter):** {overall['total_before_filter']}")
            report.append(f"- **Periods Filtered Out:** {overall.get('filtered_out_count', 0)}")
            
            # Detailed cutoff explanation
            cutoff_expl = overall.get('cutoff_explanation', {})
            cutoff_hours = cutoff_expl.get('cutoff_hours', overall.get('cutoff_days', 0) * 24)
            cutoff_minutes = cutoff_expl.get('cutoff_minutes', cutoff_hours * 60)
            
            report.append(f"- **Filter Cutoff:** {cutoff_hours:.2f} hours ({cutoff_minutes:.0f} minutes)")
            report.append(f"- **Cutoff Method:** {cutoff_expl.get('method', 'unknown')}")
            report.append(f"- **Cutoff Reason:** {cutoff_expl.get('reason', 'Not specified')}")
            
            # Show filtered out period statistics
            if overall.get('filtered_out_stats') and overall['filtered_out_stats'].get('count', 0) > 0:
                filtered_stats = overall['filtered_out_stats']
                report.append("\n**Filtered Out Periods (Below 30 Minute Threshold):**")
                report.append(f"- **Total Filtered:** {filtered_stats['count']}")
                report.append(f"- **Minimum:** {filtered_stats.get('min_minutes', 0):.2f} minutes")
                report.append(f"- **Maximum:** {filtered_stats.get('max_minutes', 0):.2f} minutes")
                report.append(f"- **Average:** {filtered_stats.get('avg_minutes', 0):.2f} minutes")
                report.append(f"- **Median:** {filtered_stats.get('median_minutes', 0):.2f} minutes")
                
                if filtered_stats.get('distribution'):
                    report.append("\n**Distribution of Filtered Out Periods:**")
                    report.append("| Time Range | Count |")
                    report.append("|------------|-------|")
                    dist_order = ['< 1 minute', '1-5 minutes', '5-10 minutes', '10-15 minutes', '15-30 minutes', '30+ minutes']
                    for bucket in dist_order:
                        count = filtered_stats['distribution'].get(bucket, 0)
                        if count > 0:
                            report.append(f"| {bucket} | {count} |")
                report.append("")
            
            # Show inflection point/gap detection if available
            if cutoff_expl.get('gap_detected'):
                gap_info = cutoff_expl['gap_detected']
                report.append("\n**Inflection Point Detection:**")
                report.append(f"- **Jump detected:** {gap_info.get('value_before_gap_minutes', 0):.2f} → {gap_info.get('value_after_gap_minutes', 0):.2f} minutes")
                report.append(f"- **Gap size:** {gap_info.get('gap_minutes', 0):.2f} minutes")
                if gap_info.get('relative_jump'):
                    report.append(f"- **Relative jump:** {gap_info.get('relative_jump', 0):.2f}x")
                report.append(f"- **Gap score:** {gap_info.get('gap_score', 0):.1f}")
                report.append(f"- **Position:** Index {gap_info.get('gap_index', 0)} in sorted data")
                report.append("")
            
            # Show percentile analysis if available
            if cutoff_expl.get('percentiles_minutes'):
                percs = cutoff_expl['percentiles_minutes']
                report.append("\n**Percentile Analysis (before filtering, in minutes):**")
                report.append(f"- 1st percentile: {percs.get('1st', 0):.2f} minutes")
                report.append(f"- 2nd percentile: {percs.get('2nd', 0):.2f} minutes")
                report.append(f"- 5th percentile: {percs.get('5th', 0):.2f} minutes")
                report.append(f"- 10th percentile: {percs.get('10th', 0):.2f} minutes")
                
                if cutoff_expl.get('jumps_minutes'):
                    jumps = cutoff_expl['jumps_minutes']
                    report.append("\n**Jump Analysis (looking for natural breakpoints, in minutes):**")
                    report.append(f"- 1st to 2nd percentile jump: {jumps.get('p1_to_p2', 0):.2f} minutes")
                    report.append(f"- 2nd to 5th percentile jump: {jumps.get('p2_to_p5', 0):.2f} minutes")
                    report.append(f"- 5th to 10th percentile jump: {jumps.get('p5_to_p10', 0):.2f} minutes")
                report.append("")
            
        report.append(f"- **Average Time:** {overall['average_days']:.2f} days ({format_timedelta(timedelta(days=overall['average_days']))})")
        report.append(f"- **Median Time:** {overall['median_days']:.2f} days ({format_timedelta(timedelta(days=overall['median_days']))})")
        report.append(f"- **Minimum Time:** {overall['min_days']:.2f} days ({format_timedelta(timedelta(days=overall['min_days']))})")
        report.append(f"- **Maximum Time:** {overall['max_days']:.2f} days ({format_timedelta(timedelta(days=overall['max_days']))})")
        report.append(f"- **Standard Deviation:** {overall['stdev_days']:.2f} days\n")
        
        # Overall time bucket distribution
        if overall.get('buckets'):
            report.append("### Overall Time Bucket Distribution\n")
            report.append("| Time Range | Count | Percentage |")
            report.append("|------------|-------|------------|")
            
            total_periods = overall['total_periods']
            bucket_order = [
                "< 1 day", "1-3 days", "3-5 days", "5-7 days",
                "1-2 weeks", "2-3 weeks", "3-4 weeks",
                "1-2 months", "2-3 months", "> 3 months"
            ]
            
            for bucket in bucket_order:
                count = overall['buckets'].get(bucket, 0)
                if count > 0:
                    pct = (count / total_periods * 100) if total_periods > 0 else 0
                    report.append(f"| {bucket} | {count} | {pct:.1f}% |")
            report.append("")
    
    if ball_times['by_assignee']:
        report.append("### Statistics by Assignee\n")
        report.append("| Assignee | Total Periods | Average Days | Median Days | Total Days |")
        report.append("|----------|---------------|--------------|-------------|------------|")
        
        sorted_assignees = sorted(
            ball_times['by_assignee'].items(),
            key=lambda x: x[1]['total_days'],
            reverse=True
        )
        
        for assignee, stats in sorted_assignees[:20]:  # Top 20
            report.append(
                f"| {assignee[:40]} | {stats['total_periods']} | "
                f"{stats['average_days']:.2f} | {stats['median_days']:.2f} | "
                f"{stats['total_days']:.2f} |"
            )
        report.append("")
        
        # Time bucket distribution by assignee
        report.append("### Time Bucket Distribution by Assignee\n")
        report.append("*Showing top 15 assignees by total periods*\n")
        
        bucket_order = [
            "< 1 day", "1-3 days", "3-5 days", "5-7 days",
            "1-2 weeks", "2-3 weeks", "3-4 weeks",
            "1-2 months", "2-3 months", "> 3 months"
        ]
        
        # Sort by total periods for bucket display
        sorted_for_buckets = sorted(
            ball_times['by_assignee'].items(),
            key=lambda x: x[1]['total_periods'],
            reverse=True
        )[:15]
        
        for assignee, stats in sorted_for_buckets:
            if stats.get('buckets'):
                report.append(f"#### {assignee[:50]}\n")
                report.append("| Time Range | Count | Percentage |")
                report.append("|------------|-------|------------|")
                
                total = stats['total_periods']
                for bucket in bucket_order:
                    count = stats['buckets'].get(bucket, 0)
                    if count > 0:
                        pct = (count / total * 100) if total > 0 else 0
                        report.append(f"| {bucket} | {count} | {pct:.1f}% |")
                report.append("")
    
    # Status Statistics
    report.append("## 3. Status Distribution and Transitions\n")
    report.append("### Current Status Distribution\n")
    report.append("| Status | Count | Percentage |")
    report.append("|--------|-------|------------|")
    
    total = status_stats['total_submittals']
    for status, count in sorted(status_stats['current_distribution'].items(), key=lambda x: x[1], reverse=True):
        pct = (count / total * 100) if total > 0 else 0
        report.append(f"| {status} | {count} | {pct:.1f}% |")
    report.append("")
    
    if status_stats['transitions']:
        report.append("### Status Transitions (Most Common)\n")
        report.append("| Transition | Count |")
        report.append("|------------|-------|")
        for transition, count in sorted(status_stats['transitions'].items(), key=lambda x: x[1], reverse=True)[:15]:
            report.append(f"| {transition} | {count} |")
        report.append("")
    
    # Project Statistics
    report.append("## 4. Project-Level Statistics\n")
    report.append("### Top Projects by Submittal Count\n")
    report.append("| Project Name | Project ID | Total Submittals | Unique Statuses | Unique Assignees |")
    report.append("|--------------|------------|------------------|-----------------|-------------------|")
    
    for project in project_stats['projects'][:20]:  # Top 20
        report.append(
            f"| {project['project_name'] or 'N/A'} | {project['project_id']} | "
            f"{project['total_submittals']} | {project['unique_statuses']} | "
            f"{project['unique_assignees']} |"
        )
    report.append("")
    
    # Type Statistics
    report.append("## 5. Submittal Type Distribution\n")
    report.append("| Type | Count | Percentage |")
    report.append("|------|-------|------------|")
    
    total_types = type_stats['total']
    for sub_type, count in sorted(type_stats['distribution'].items(), key=lambda x: x[1], reverse=True):
        pct = (count / total_types * 100) if total_types > 0 else 0
        report.append(f"| {sub_type} | {count} | {pct:.1f}% |")
    report.append("")
    
    # Additional Metrics
    report.append("## 6. Additional Operational Metrics\n")
    report.append(f"- **Average Age of Open Submittals:** {additional_metrics['average_open_age_days']:.2f} days")
    report.append(f"- **Submittals Created in Last 30 Days:** {additional_metrics['recent_submittals_30d']}")
    report.append(f"- **Submittals Updated in Last 7 Days:** {additional_metrics['recently_updated_7d']}\n")
    
    # Current Ball in Court Distribution
    if additional_metrics['ball_in_court_distribution']:
        report.append("### Current Ball in Court Distribution\n")
        report.append("| Assignee | Count |")
        report.append("|----------|-------|")
        for assignee, count in sorted(additional_metrics['ball_in_court_distribution'].items(), key=lambda x: x[1], reverse=True)[:15]:
            report.append(f"| {assignee[:50]} | {count} |")
        report.append("")
    
    report.append("---\n")
    report.append(f"*Report generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}*\n")
    
    return "\n".join(report)


def get_database_info(app) -> str:
    """Get database connection info for debugging (sanitized)."""
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "unknown")
    
    # Sanitize the URI to hide sensitive info but show enough to identify the database
    if db_uri.startswith("sqlite"):
        # SQLite - show the path
        return f"SQLite: {db_uri}"
    elif db_uri.startswith("postgresql"):
        # PostgreSQL - parse and show host/database name
        try:
            from urllib.parse import urlparse
            parsed = urlparse(db_uri)
            host = parsed.hostname or "unknown"
            port = f":{parsed.port}" if parsed.port else ""
            database = parsed.path.lstrip("/") if parsed.path else "unknown"
            return f"PostgreSQL: {host}{port}/{database}"
        except Exception:
            return f"PostgreSQL: {db_uri.split('@')[1] if '@' in db_uri else 'unknown'}"
    elif db_uri.startswith("mysql"):
        # MySQL - parse and show host/database name
        try:
            from urllib.parse import urlparse
            parsed = urlparse(db_uri)
            host = parsed.hostname or "unknown"
            port = f":{parsed.port}" if parsed.port else ""
            database = parsed.path.lstrip("/") if parsed.path else "unknown"
            return f"MySQL: {host}{port}/{database}"
        except Exception:
            return f"MySQL: {db_uri.split('@')[1] if '@' in db_uri else 'unknown'}"
    else:
        # Unknown format - show first part only
        return f"Database: {db_uri.split('://')[0] if '://' in db_uri else 'unknown'}"


def main():
    """Main function to run the analysis."""
    app = create_app()
    
    with app.app_context():
        print("=" * 80)
        print("Procore Submittals Operations Analysis")
        print("=" * 80)
        print()
        
        # Debug: Show database connection info
        db_info = get_database_info(app)
        print(f"[DEBUG] Database Connection: {db_info}")
        print()
        
        # Run all analyses
        lifespans = calculate_submittal_lifespans()
        # Calculate project stats for both "all" and "true_create" sets
        all_project_stats = calculate_project_lifespan_statistics(lifespans.get('all', {}).get('details', []))
        true_create_project_stats = calculate_project_lifespan_statistics(lifespans.get('true_create', {}).get('details', []))
        ball_times = calculate_ball_in_court_times()
        status_stats = calculate_status_statistics()
        project_stats = calculate_project_statistics()
        type_stats = calculate_type_statistics()
        additional_metrics = calculate_additional_metrics()
        
        # Generate markdown report
        markdown = generate_markdown_report(
            lifespans, ball_times, status_stats,
            project_stats, type_stats, additional_metrics,
            all_project_stats, true_create_project_stats
        )
        
        # Write markdown file
        output_file = f"submittals_operations_analysis_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.md"
        with open(output_file, 'w') as f:
            f.write(markdown)
        
        print(f"\n✓ Analysis complete!")
        print(f"✓ Markdown report saved to: {output_file}")
        
        # Optionally generate PDF (requires markdown2 and weasyprint)
        try:
            import markdown2
            from weasyprint import HTML, CSS
            
            # Convert markdown to HTML
            html_content = markdown2.markdown(markdown, extras=['tables', 'fenced-code-blocks'])
            
            # Add basic styling for better PDF appearance
            styled_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        margin: 40px;
                        color: #333;
                    }}
                    h1, h2, h3 {{
                        color: #2c3e50;
                        margin-top: 30px;
                    }}
                    table {{
                        border-collapse: collapse;
                        width: 100%;
                        margin: 20px 0;
                    }}
                    th, td {{
                        border: 1px solid #ddd;
                        padding: 8px;
                        text-align: left;
                    }}
                    th {{
                        background-color: #4CAF50;
                        color: white;
                    }}
                    tr:nth-child(even) {{
                        background-color: #f2f2f2;
                    }}
                    code {{
                        background-color: #f4f4f4;
                        padding: 2px 4px;
                        border-radius: 3px;
                    }}
                </style>
            </head>
            <body>
                {html_content}
            </body>
            </html>
            """
            
            pdf_file = output_file.replace('.md', '.pdf')
            HTML(string=styled_html).write_pdf(pdf_file)
            print(f"✓ PDF report saved to: {pdf_file}")
        except ImportError as e:
            print("\nNote: PDF generation requires 'markdown2' and 'weasyprint' packages.")
            print("Install with: pip install markdown2 weasyprint")
            print("Markdown file is still available.")
        except Exception as e:
            error_msg = str(e)
            print(f"\nNote: PDF generation failed: {error_msg}")
            print("Markdown file is still available.")
            
            # Provide helpful guidance for common errors
            if 'libgobject' in error_msg.lower() or 'gobject' in error_msg.lower():
                print("\nPDF generation requires system libraries on macOS.")
                print("To fix this, install GTK+ libraries using Homebrew:")
                print("  brew install cairo pango gdk-pixbuf libffi")
                print("\nOr use an alternative method:")
                print("  - Open the markdown file in a markdown viewer and export as PDF")
                print("  - Use pandoc: pandoc report.md -o report.pdf")
                print("  - Use an online markdown to PDF converter")
            elif 'weasyprint' in error_msg.lower():
                print("\nWeasyPrint may require additional system dependencies.")
                print("See: https://weasyprint.org/install/")
        
        print("\n" + "=" * 80)


if __name__ == "__main__":
    main()

