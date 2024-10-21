from app import create_app, db
from app.models import User

app = create_app()

def create_auth_user():
    with app.app_context():
        username = input("Enter username: ")
        email = input("Enter email: ")
        password = input("Enter password: ")
        is_authorizer = input("Make this user an authorizer? (y/n): ").lower() == 'y'

        new_user = User(username=username, email=email, is_authorizer=is_authorizer)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        print(f"User created with id: {new_user.id}")
        print(f"Authorizer status: {'Yes' if new_user.is_authorizer else 'No'}")

if __name__ == "__main__":
    create_auth_user()