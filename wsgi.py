from app import create_app, socketio

app = create_app()

# Export socketio for gunicorn with eventlet workers
# When using gunicorn with eventlet workers, use: gunicorn --worker-class eventlet -w 1 wsgi:app
# The socketio object is needed for proper websocket handling
