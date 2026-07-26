"""T&M tickets — native mobile creation of Time & Material field tickets.

The live path is native digital creation: a foreman keys a ticket on a device
(labor/materials/equipment, location, work description), saved as a draft that
moves through the create→sign→approve→CO lifecycle in later phases. See
service.py for the lifecycle and routes.py for the HTTP surface.

The legacy-paper vision-ingestion path (extract.py + service.create_from_upload)
is PARKED — retained for a future "photograph a paper ticket" import, with no
HTTP route exposing it.
"""
