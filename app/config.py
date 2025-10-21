import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    TRELLO_API_KEY = os.environ.get("TRELLO_API_KEY")
    TRELLO_TOKEN = os.environ.get("TRELLO_TOKEN")
    TRELLO_BOARD_ID = os.environ.get("TRELLO_BOARD_ID")
    NEW_TRELLO_CARD_LIST_ID = os.environ.get("NEW_TRELLO_CARD_LIST_ID")
    AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")
    AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
    AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
    ONEDRIVE_USER_EMAIL = os.environ.get("ONEDRIVE_USER_EMAIL")
    ONEDRIVE_FILE_PATH = os.environ.get("ONEDRIVE_FILE_PATH")
    TRELLO_WEBHOOK_URL = os.environ.get("TRELLO_WEBHOOK_URL")
    ONEDRIVE_WEBHOOK_URL = os.environ.get("ONEDRIVE_WEBHOOK_URL")
    EXCEL_INDEX_ADJ = (
        4  # Adjust for header rows in Excel (e.g., if data starts on row 5, this is 4)
    )