import os


class Config:
    TRELLO_API_KEY = os.environ.get("TRELLO_API_KEY")
    TRELLO_TOKEN = os.environ.get("TRELLO_TOKEN")
    TRELLO_BOARD_ID = os.environ.get("TRELLO_BOARD_ID")
    AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")
    AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
    AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
