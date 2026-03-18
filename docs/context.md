# Event Deduplication Bug
It appears we have a bug in event deduplication. When testing, we often move stages back and forth in the Job Log 2.0 to see how it affects the UI and Trello. The current event deduplication system blocks this back and forth.

# Tasks
- Report how event deduplication for ReleaseEvents is currently implemented. 
- Provide solutions for making deduplication improvments related to bug.
