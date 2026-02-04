# Procore Submittals Operations Analysis Script

## Overview

The `analyze_submittals_operations.py` script provides comprehensive analysis of Procore submittals data, including:

- **Average submittal lifespan** from creation to status "Closed"
- **Average ball in court times** for each assignee
- **Status distribution and transitions**
- **Project-level statistics**
- **Type-level statistics**
- **Additional operational metrics**

## Usage

### Basic Usage

```bash
cd /path/to/trello_sharepoint
python scripts/analyze_submittals_operations.py
```

The script will:
1. Connect to the database
2. Analyze all submittal data
3. Generate a markdown report with timestamp: `submittals_operations_analysis_YYYYMMDD_HHMMSS.md`

### Output Format

The script generates a markdown file by default. The report includes:

1. **Executive Summary** - High-level statistics
2. **Submittal Lifespan Analysis** - Average, median, min, max lifespans
3. **Ball in Court Time Analysis** - Overall and per-assignee statistics
4. **Status Distribution** - Current statuses and common transitions
5. **Project-Level Statistics** - Top projects by submittal count
6. **Type Distribution** - Submittal types breakdown
7. **Additional Metrics** - Recent activity, open submittal ages, etc.

### PDF Generation (Optional)

The script attempts to generate a PDF version if the required packages are installed:

```bash
pip install markdown2 weasyprint
```

If PDF generation fails, the markdown file is still created.

## Requirements

- Python 3.7+
- Flask application context (database connection)
- SQLAlchemy models: `ProcoreSubmittal`, `SyncOperation`, `SyncLog`

## Analysis Details

### Submittal Lifespan

Calculates the time from submittal creation (`created_at`) to when the status changed to "Closed" (tracked via `SyncLog` entries for status changes).

### Ball in Court Times

Tracks how long each assignee had the ball in court by analyzing:
- `SyncOperation` records with type `procore_ball_in_court`
- `SyncLog` entries with `old_value` and `new_value` for ball_in_court changes
- Calculates duration between changes

### Status Transitions

Analyzes common status transitions by examining:
- Status change operations
- Old value → New value patterns

## Example Output

```
# Procore Submittals Operations Analysis Report

**Generated:** 2024-01-15 14:30:00 UTC

---

## Executive Summary

- **Total Submittals:** 1,234
- **Closed Submittals:** 456
- **Open Submittals:** 778
- **Total Projects:** 25
- **Recent Activity (30 days):** 45 new submittals
- **Recent Updates (7 days):** 123 submittals updated

## 1. Submittal Lifespan Analysis

### Average Lifespan: Creation to Closed

- **Total Closed Submittals Analyzed:** 456
- **Average Lifespan:** 45.2 days (1 month, 15 days)
- **Median Lifespan:** 38.5 days (1 month, 8 days)
...
```

## Notes

- The script uses UTC timestamps for all calculations
- Ongoing ball in court assignments are calculated up to the current time
- Only submittals with valid timestamps are included in calculations
- The script handles missing or null data gracefully

## Troubleshooting

### Database Connection Issues

Ensure you're running the script from the project root and that the Flask app can connect to the database:

```bash
export FLASK_APP=run.py
python scripts/analyze_submittals_operations.py
```

### Missing Data

If certain metrics show 0 or N/A:
- Check that `SyncOperation` and `SyncLog` records exist for the metrics you're interested in
- Verify that submittals have been updated via webhooks (which create these log entries)
- Some metrics require historical data - ensure webhooks have been active for sufficient time

### PDF Generation Issues

If PDF generation fails:
- The markdown file is still created and can be converted manually
- Use tools like Pandoc: `pandoc report.md -o report.pdf`
- Or open the markdown in a markdown viewer that supports PDF export

