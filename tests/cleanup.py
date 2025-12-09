from django.contrib.sessions.models import Session
from core.models import CustomUser  # Import your custom user model

# Check if user ID=3 exists
try:
    user = CustomUser.objects.get(id=3)
    print(f"User exists: {user.email}")
except CustomUser.DoesNotExist:
    print("User ID=3 doesn't exist in CustomUser database")

# Find and delete sessions for non-existent users
for session in Session.objects.all():
    try:
        data = session.get_decoded()
        user_id = data.get('_auth_user_id')
        if user_id and not CustomUser.objects.filter(id=user_id).exists():
            print(f"Deleting session {session.session_key} for non-existent user {user_id}")
            session.delete()
    except Exception as e:
        print(f"Error processing session {session.session_key}: {str(e)}")
        continue