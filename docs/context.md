# Fab Order Multi Select + Bug Fixes
Fab ordering on the job log is still a little goofy
We also want to allow several releases to land on the same fab order number in the 3-X bucket

# Fab Order Same # Multi
- For releases with fab order 3-X, we want to allow different releases to have the same fab number
- In the case that multiple releases have the same fab order number, we flag this by filling the background of the specific fab order cells with an orange color.
- We do not block fab order number collisions, we simply track them.
- CORRECTION this is for fab order 4-X, fab orders 1-2-3 are static and should not color.

# Fab Order Bugs
- When changing fab order stage, we still sometimes order a release to the very bottom of the releases table regardless of stage
- Example, release moving from 'Released' - 'Fit Up' should go from 45 -> 37 or something and instead goes 45 -> 127 and bottom of list. 
- This appears to only happen on stage changes, intra stage changes appear to be shuffling correctly.

# Ask Clarifying Questions, make no assumptions about fab ordering. I can provide more detail if you have any confusion about any fab order related behaviors.
