# test_auth.py
import os
import django
import sys

# Setup Django
sys.path.append('/home/devmaniac/Desktop/theLearning')  # Update this
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'theLearning.settings')
django.setup()

from django.contrib.auth import get_user_model, authenticate
from core.models import CustomUser

User = get_user_model()

print("=" * 50)
print("AUTHENTICATION DEBUGGING")
print("=" * 50)

# 1. Check if any users exist
users = User.objects.all()
print(f"Total users in database: {users.count()}")
for user in users:
    print(f"  - {user.email} (ID: {user.id}, Active: {user.is_active})")

# 2. Try to authenticate a known user
if users.exists():
    test_user = users.first()
    print(f"\nTesting authentication for: {test_user.email}")

    # Manual authentication
    auth_user = authenticate(email=test_user.email, password='testpassword')
    if auth_user:
        print(f"✓ Authentication successful: {auth_user.email}")
        print(f"  User is active: {auth_user.is_active}")
        print(f"  User is staff: {auth_user.is_staff}")
    else:
        print("✗ Authentication failed")

        # Check password manually
        from django.contrib.auth.hashers import check_password

        password_matches = check_password('testpassword', test_user.password)
        print(f"  Password matches hash: {password_matches}")

        # Check authentication backends
        from django.contrib.auth import get_backends

        print("\nTesting authentication backends:")
        for backend in get_backends():
            print(f"  Backend: {backend.__class__.__name__}")
            try:
                result = backend.authenticate(
                    request=None,
                    email=test_user.email,
                    password='testpassword'
                )
                print(f"    Result: {result}")
            except Exception as e:
                print(f"    Error: {e}")

# 3. Create a test user if none exists
if not users.exists():
    print("\nCreating test user...")
    test_user = User.objects.create_user(
        email='test@example.com',
        password='TestPass123',
        first_name='Test'
    )
    print(f"Test user created: {test_user.email}")