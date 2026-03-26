# Issues
- Job Log Staging not accurately representing Release staging from Onedrive
- Trello card creations from onedrive poller broken
- Need a way to identify releases with missing Trello card to programatically add them back

# Complications
Onedrive polling system is passable at best. We continue to have issues syncing Excel rows and Trello cards. It appears that the onedrive system is no longer creating Trello cards when a new row is detected. A bug fix there would be helpful. Additionally, we need a script that identifies which releases are currently active given the onedrive snapshots, compares that against the releases table as we have old rows in the releases table, and then makes that comparison to the Trello board to see which confirmed jobs table + releases table rows are missing Trello cards.


