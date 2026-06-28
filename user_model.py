# models/user_model.py

from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.email = user_data['email']
        self.role = user_data['role']
        self.is_approved = user_data.get('is_approved', False)  # For doctors