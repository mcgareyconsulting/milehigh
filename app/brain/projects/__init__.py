"""Projects read-model package.

Read-only rollups that turn a `Projects` geofence row + its value-joined
`Releases` / `Submittals` / event streams into the shape the Projects tab
renders. No writes, no external calls — SELECTs only.
"""
