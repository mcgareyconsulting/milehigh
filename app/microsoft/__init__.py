"""Microsoft Graph integration (app-only / client-credentials).

Holds the shared Graph client used to read a dedicated mailbox/calendar
(e.g. bb@mhmw.com) as an application — the workaround for not opening Graph
across the whole org. The app is scoped to that mailbox via an Azure
ApplicationAccessPolicy. See graph_app_client.py.
"""
