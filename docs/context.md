# Onedrive Tune Up
This branch contains the merge I am working toward between main and my outpaced sandbox with new features.
We need to confirm that the Onedrive Excel Poller is working on the scheduler and passing information correctly.

# Onedrive
- Onedrive run diffs against 'jobs' db table 
- Then we hit the Trello API to update the card(s).
- We write this event in Ops and Logs in DB

# Trello Webhooks
- Webhooks currently disabled, previously writing back to Onedrive
- Webhooks need to be updated to hit ReleaseEvents with source 'Trello' and the 'releases' table to update job log 2.0

# Job Log 2.0
- New version of Onedrive effectively
- Built on top of 'releases' table
- Will accept and update based on Trello Webhooks
- Will accept user actions that update 'releases' table
- No outbound to Trello for now

# Releases Table
- Need to run a script that builds 'stage', 'stage_group', and 'banana_color'. This may exist somewhere already

# Goal
Onedrive is being deprecated, but in the short term must continue to operate. Therefore, we will use new Job Log 2.0 as a shadow mode that will handle Trello Webhooks, so it's semi live. Job Log actions update the 'releases' table, but all outbound to Trello API should be disabled. Must confirm that Onedrive scheduler is working and passing to Trello API. Must confirm that Trello Hooks are hitting Release Events and updating 'releases' table. 
