# Implicit Stage Fab Ordering
Stage and fab order confusion on job log needs cleanup. We will provide an implicit soft-lock fab ordering per stage. Example, welded jobs hold fab order 9-13, fit up comp which is one step before welded cannot hold a value greater than 14. 

# Backend
- Build tighter logical constraints on fab ordering. There should be no intermingling of releases because a fab order outpaces. 
- Ask clarifying questions but structured fab ordering on stage order should make sense.


