"""Database configuration and setup for different environments."""
import os


def get_database_engine_options():
    """Get database engine options for PostgreSQL connections."""
    from sqlalchemy.pool import QueuePool
    
    return {
        "pool_pre_ping": True,        # Detect and refresh dead connections before use
        "pool_recycle": 280,          # Recycle connections slightly before Render's idle timeout (~5 min)
        "pool_size": 5,               # Render free-tier DBs are resource-constrained; keep this modest
        "max_overflow": 10,           # Allow some burst usage during concurrent jobs
        "pool_timeout": 30,           # Wait up to 30s for a connection before raising
        "pool_reset_on_return": "commit",  # Reset connections properly on return
        "poolclass": QueuePool,       # Use QueuePool for standard threading
        "connect_args": {
            "sslmode": "require",     # Enforce SSL
            "connect_timeout": 10,    # Fail fast if DB can't be reached
            "application_name": "trello_sharepoint_app",
            "options": "-c statement_timeout=30000"  # 30s max per SQL statement
        },
    }


def get_local_database_config():
    """Get database configuration for local development.
    
    Returns:
        tuple: (database_uri, engine_options)
    """
    database_uri = os.environ.get("LOCAL_DATABASE_URL") or "sqlite:///jobs.sqlite"
    engine_options = None  # SQLite doesn't need engine options
    return database_uri, engine_options


def get_sandbox_database_config():
    """Get database configuration for sandbox/staging environment.
    
    Returns:
        tuple: (database_uri, engine_options)
        
    Raises:
        ValueError: If database URL is not configured
    """
    database_url = os.environ.get("SANDBOX_DATABASE_URL")
    if not database_url:
        raise ValueError("SANDBOX_DATABASE_URL or DATABASE_URL must be set for sandbox environment")
    
    engine_options = get_database_engine_options()
    return database_url, engine_options


def get_production_database_config():
    """Get database configuration for production environment.
    
    Returns:
        tuple: (database_uri, engine_options)
        
    Raises:
        ValueError: If database URL is not configured
    """
    database_url = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("PRODUCTION_DATABASE_URL or DATABASE_URL must be set for production environment")
    
    engine_options = get_database_engine_options()
    return database_url, engine_options


def get_database_config(environment=None):
    """Get database configuration based on environment.
    
    Args:
        environment: Environment name ('local', 'sandbox', 'production')
                    If None, will be determined from ENVIRONMENT or FLASK_ENV env vars.
    
    Returns:
        tuple: (database_uri, engine_options)
    """
    if environment is None:
        environment = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT", "local")
        environment = environment.lower()
    
    if environment in ["local", "development", "dev"]:
        return get_local_database_config()
    elif environment in ["sandbox", "staging", "stage"]:
        return get_sandbox_database_config()
    elif environment in ["production", "prod"]:
        return get_production_database_config()
    else:
        # Default to local for safety
        return get_local_database_config()


def configure_database(app):
    """Configure database settings for the Flask app.
    
    This function sets SQLALCHEMY_DATABASE_URI and SQLALCHEMY_ENGINE_OPTIONS
    on the app config based on the current environment.
    
    Args:
        app: Flask application instance
    """
    # Get environment
    environment = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT", "local")
    environment = environment.lower()
    
    # Get database configuration
    database_uri, engine_options = get_database_config(environment)
    
    # Set Flask config
    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ECHO"] = False  # Set to True for SQL query debugging
    
    if engine_options:
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options
