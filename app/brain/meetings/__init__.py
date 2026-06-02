"""Meeting ingestion (stubbed) + post-meeting checklist → to-do/notify.

MVP of the Hive Mind "meeting → checklist → to-do/notify" flow:
  transcript in → extractor proposes checklist items → reviewer (Bill) curates
  (yes/no/edit, owner + due date editable) → accepted items notify their owner
  as the due date approaches.

Ingestion is stubbed (transcript pasted via the API); the Recall.ai/Teams adapters
land here later behind the same boundary.
"""
