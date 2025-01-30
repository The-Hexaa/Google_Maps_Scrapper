from flask_sqlalchemy import SQLAlchemy
from flask import Flask
from uuid import uuid4
from werkzeug.security import generate_password_hash, check_password_hash
import sys
sys.stdout.reconfigure(line_buffering=True)

# Initialize the database object
db = SQLAlchemy()

class User(db.Model):
    # Define the table name (optional but good practice)
    __tablename__ = 'users'
    
    # Fields in the User table
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True, nullable=False)  # Auto-incrementing user_id
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    # Constructor to initialize the user object
    def __init__(self, name, email, password):
        self.user_id = str(uuid4())  # Generate a unique user_id using uuid
        self.name = name
        self.email = email
        self.password = generate_password_hash(password)  # Hash the password when saving to DB

    # Method to check if the entered password matches the stored one
    def check_password(self, password):
        return check_password_hash(self.password, password)

    # Representation for easy inspection in the debugger or logs
    def __repr__(self):
        return f"<User {self.name}, Email: {self.email}>"
