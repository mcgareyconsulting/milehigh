# Fab Order Ordering 
Bug in fab ordering on the job log -> releases table

# Staging
All staging barriers seem to be working appropriately. The goal is that fab order does not mix across stages. Welded QC -> Welded -> ... -> Released has a clear 3-X list.

# Manual Fab Ordering
## Bug
- Updating the Fab Order of one release triggers a cascade that reorders all releases and resulted in bleeding extra releases into the job log. I changed 40-41 for one release in 'Released' stage. So one step fab order change for one release reordered ALL releases and bloated 50 records to the job log? Went from 273 active releases to 323 listed after the reordering completed. Not what we are looking for.

## Goal
- User will need to make small step reordering changes. So 30 needs bumped to 27 or something like that. We want to move 30 to 27 and bump 27-28-29 down one respectively. There should be no global cascading effect. If a release's stage is changed, it should bump to N+1 for the 3-X fab order number subset that the new stage occupies at that time.

# Ask Clarifying Questions
