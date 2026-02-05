"""
Add 3 dedicated test users to the database.

Usage:
    python migrations/add_test_users.py

This script will prompt you for the username and password for each of the 3 users.
Users will be created with is_active=True. You can optionally set is_admin for each user.
"""

import sys
import os

# Add parent directory to path to import app modules
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from app import create_app
from app.models import User, db
from app.auth.utils import hash_password


def mask_database_url(url):
    """Mask sensitive parts of database URL for display."""
    if not url:
        return "Not set"
    
    # Mask passwords in URLs (postgresql://user:password@host/db)
    if '@' in url:
        parts = url.split('@')
        if ':' in parts[0]:
            # Has credentials
            scheme_user = parts[0]
            rest = '@' + parts[1] if len(parts) > 1 else ''
            if '://' in scheme_user:
                scheme, user_pass = scheme_user.split('://', 1)
                if ':' in user_pass:
                    user, _ = user_pass.split(':', 1)
                    return f"{scheme}://{user}:***{rest}"
        return url
    return url


def add_test_users():
    """Add 3 test users to the database."""
    app = create_app()
    
    with app.app_context():
        # Get database information
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', 'Not set')
        environment = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT", "local")
        
        # Get existing user count
        existing_user_count = User.query.count()
        
        print("=" * 60)
        print("Adding 3 Test Users")
        print("=" * 60)
        print()
        print("Database Configuration:")
        print(f"  Environment: {environment}")
        print(f"  Database URI: {mask_database_url(db_uri)}")
        print(f"  Current users in database: {existing_user_count}")
        print()
        print("⚠ WARNING: This will add users to the database shown above.")
        print()
        
        # Ask for confirmation
        confirm = input("Do you want to continue? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("✗ Cancelled. No users were added.")
            return False
        
        print()
        print("=" * 60)
        print("Enter User Information")
        print("=" * 60)
        print()
        
        users_data = []
        
        # Collect user information
        for i in range(1, 4):
            print(f"User {i}:")
            username = input(f"  Username: ").strip()
            if not username:
                print("  ✗ Username cannot be empty. Skipping this user.")
                continue
            
            password = input(f"  Password: ").strip()
            if not password:
                print("  ✗ Password cannot be empty. Skipping this user.")
                continue
            
            is_admin_input = input(f"  Is admin? (y/n, default: n): ").strip().lower()
            is_admin = is_admin_input == 'y'
            
            users_data.append({
                'username': username,
                'password': password,
                'is_admin': is_admin
            })
            print()
        
        if not users_data:
            print("✗ No users to add.")
            return False
        
        # Create users
        created_count = 0
        skipped_count = 0
        
        for user_data in users_data:
            username = user_data['username']
            
            # Check if user already exists
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                print(f"⚠ User '{username}' already exists. Skipping.")
                skipped_count += 1
                continue
            
            # Create new user
            try:
                new_user = User(
                    username=username,
                    password_hash=hash_password(user_data['password']),
                    is_admin=user_data['is_admin'],
                    is_active=True
                )
                
                db.session.add(new_user)
                db.session.commit()
                
                print(f"✓ Created user '{username}' (admin: {user_data['is_admin']})")
                created_count += 1
                
            except Exception as e:
                print(f"✗ Error creating user '{username}': {e}")
                db.session.rollback()
        
        print()
        print("=" * 60)
        print(f"Summary: {created_count} created, {skipped_count} skipped")
        print("=" * 60)
        
        return created_count > 0


if __name__ == "__main__":
    try:
        success = add_test_users()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n✗ Cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

