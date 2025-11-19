import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    TRELLO_API_KEY = os.environ.get("TRELLO_API_KEY")
    TRELLO_TOKEN = os.environ.get("TRELLO_TOKEN")
    TRELLO_BOARD_ID = os.environ.get("TRELLO_BOARD_ID")
    NEW_TRELLO_CARD_LIST_ID = os.environ.get("NEW_TRELLO_CARD_LIST_ID")
    FIT_UP_COMPLETE_LIST_ID = os.environ.get("FIT_UP_COMPLETE_LIST_ID")
    UNASSIGNED_CARDS_LIST_ID = os.environ.get("UNASSIGNED_CARDS_LIST_ID")
    FAB_ORDER_FIELD_ID = os.environ.get("FAB_ORDER_FIELD_ID")
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
    SNAPSHOTS_DIR = os.environ.get("SNAPSHOTS_DIR", "excel_snapshots")  # Default to local dir, use /var/data/ in production

    # Sandbox Procore
    PROCORE_ACCESS_TOKEN = os.environ.get("PROCORE_ACCESS_TOKEN")
    PROCORE_SANDBOX_BASE_URL = os.environ.get("PROCORE_SANDBOX_BASE_URL")

    # Production Procore
    PROD_PROCORE_COMPANY_ID = os.environ.get("PROD_PROCORE_COMPANY_ID")
    PROD_PROCORE_BASE_URL = os.environ.get("PROD_PROCORE_BASE_URL")
    PROD_PROCORE_AUTH_CODE = os.environ.get("PROD_PROCORE_AUTH_CODE")
    PROD_PROCORE_CLIENT_ID = os.environ.get("PROD_PROCORE_CLIENT_ID")
    PROD_PROCORE_CLIENT_SECRET = os.environ.get("PROD_PROCORE_CLIENT_SECRET")
    PROD_PROCORE_ACCESS_TOKEN = os.environ.get("PROD_PROCORE_ACCESS_TOKEN")
    PROD_PROCORE_REFRESH_TOKEN = os.environ.get("PROD_PROCORE_REFRESH_TOKEN")

    # Procore Webhook
    PROCORE_DEV_WEBHOOK_URL = os.environ.get("PROCORE_DEV_WEBHOOK_URL")
    PROCORE_PROD_WEBHOOK_URL = os.environ.get("PROCORE_PROD_WEBHOOK_URL")
