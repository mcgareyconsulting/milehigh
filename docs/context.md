# Job Comp / Invoiced Columns Improvements
Job Comp interaction with Status Complete and Job Comp / Invoiced column behavior is slightly off relative to desired outcomes.

# Job Comp / Invoiced Numerical values
- when a number is placed in the job comp or invoiced columns '90' we want to mask or update this value to show 90%. Currently, we are accepting 0.9, which mathematically is equivalent, but the user wants a differnet view.
- User will enter 90 in the Job Comp cell for a particular release. This hsould as 90%. Obviously the start install timings etc should not have their math affected.

# Job Comp <-> Complete Status
- Currently an 'X' in Job Comp or Status 'Complete' will affect the other 'X' -> 'Complete' or 'Complete' -> 'X'
- If we are 'X' and 'Complete' and the 'X' is removed from Job Comp or the status is changed away from 'Complete' the other column must reflect this change. There is a bug where status is 'Complete' and then changed back, but the 'X' in Job Comp is retained incorrectly.

# UI behavior
- I also want to confirm that an 'X' in Job Comp will gray out the row, but a row is not collected in the Archive function until Job Comp and Invoiced both show 'X'


# Ask Clarifying Questionzs
