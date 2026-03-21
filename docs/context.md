# Job Comp - Invoiced - Send to Archive
Handling of complete jobs / archived jobs is not perfect.

# Job Comp
When a release has value 'X' in Job Comp column or value 'Complete' in Stage dropdown, we drop fab order number and gray the row out.
If 'X' placed in Job Comp, change stage to 'Complete'. Vice Versa.

# Invoiced
When a release has value 'X' in Invoiced column, take no immediate action

# Send to Archive
Currently, releases are sent to archive when Job Comp and Invoiced have X and some amount of time has passed since this release went XX.
FIX: Actions needs a send to Archive button. This will pull a preview of releases with job Comp X and nvocied X on the active Job Log. A preview modal will pull up with a confirmation message, 'Confirm sending x releases to archive. This should be an admin only functionality.

# Ask Clarifying Questions
