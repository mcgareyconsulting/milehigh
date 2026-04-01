# Fab Ordering Bug
I have a continual fab ordering bug on the job log. When a release moves stages, say 'Released' to 'Fit Up Complete.' I want the fab order for that release to snap to the bottom of its newly assigned stage. Let's say its 45 but jumps into a stage with values 12-28. The newly moved stage should snap to 29.

# Bugs
The last two versions have had very different bugs. usually, the stage move shoves the release to the bottom of the table, like 15 -> 128, wild.
Now, for whatever reason, I am getting 0s and -1s when changing a releases stage.

# Current Functionality
- Every release with a stage in the fabrication group needs a fab order number in the subset 4-X where X is number of releases in fabrication group. We are allowing duplicates, these are tagged orange and acceptable. There is currently no cascade effect if a release is changed from 13-12, we accept the duplicate on 12 without reording the old 12 release.

# Goal
I do not want stage crossover when filtering by fab orders right. So i want to be able to run all my filtes off of fab order without stage bleed. Example of stage bleed: Fab order 13-14-15 would be stages Paint complete - Welded - Paint complete. we do not want this, there should be clear separation between stages aroudn the fab order, which is the purpose of the stage bounding.

# Ask Clarifying Questions
