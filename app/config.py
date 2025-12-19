import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration class with common settings."""
    # Trello configuration
    TRELLO_API_KEY = os.environ.get("TRELLO_API_KEY")
    TRELLO_TOKEN = os.environ.get("TRELLO_TOKEN")
    TRELLO_BOARD_ID = os.environ.get("TRELLO_BOARD_ID")
    NEW_TRELLO_CARD_LIST_ID = os.environ.get("NEW_TRELLO_CARD_LIST_ID")
    FIT_UP_COMPLETE_LIST_ID = os.environ.get("FIT_UP_COMPLETE_LIST_ID")
    UNASSIGNED_CARDS_LIST_ID = os.environ.get("UNASSIGNED_CARDS_LIST_ID")
    FAB_ORDER_FIELD_ID = os.environ.get("FAB_ORDER_FIELD_ID")
    TRELLO_WEBHOOK_URL = os.environ.get("TRELLO_WEBHOOK_URL")
    
    # Azure configuration
    AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")
    AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
    AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
    # NOTE: OneDrive/Excel functionality removed - ONEDRIVE_* and SNAPSHOTS_DIR config removed
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
    PROCORE_SANDBOX_WEBHOOK_URL = os.environ.get("PROCORE_SANDBOX_WEBHOOK_URL")
    
    # CORS configuration
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
    
    # Admin PIN for health scan admin page
    ADMIN_PIN = os.environ.get("ADMIN_PIN", "1234")


class LocalConfig(Config):
    """Configuration for local development."""
    ENV = "local"
    DEBUG = True


class SandboxConfig(Config):
    """Configuration for sandbox/staging environment."""
    ENV = "sandbox"
    DEBUG = False


class ProductionConfig(Config):
    """Configuration for production environment."""
    ENV = "production"
    DEBUG = False


def get_config():
    """Get the appropriate configuration class based on environment variable.
    
    Environment is determined by FLASK_ENV or ENVIRONMENT variable:
    - 'local' or 'development' -> LocalConfig
    - 'sandbox' or 'staging' -> SandboxConfig
    - 'production' or 'prod' -> ProductionConfig
    
    Defaults to LocalConfig if not set.
    """
    env = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT", "local").lower()
    
    if env in ["local", "development", "dev"]:
        return LocalConfig
    elif env in ["sandbox", "staging", "stage"]:
        return SandboxConfig
    elif env in ["production", "prod"]:
        return ProductionConfig
    else:
        # Default to local for safety
        return LocalConfig
