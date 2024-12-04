from app import create_app, db
from app.models import User
from sqlalchemy.exc import IntegrityError

app = create_app()

def create_auth_user():
    with app.app_context():
        try:
            # First check if database tables exist
            db.create_all()
        except Exception as e:
            print(f"Database initialization error: {str(e)}")
            return

        while True:
            try:
                # Get username
                username = input("Enter username: ").strip()
                if not username:
                    print("Username cannot be empty")
                    continue
                if User.query.filter_by(username=username).first():
                    print("Username already exists. Please choose another.")
                    continue
                
                # Get email
                email = input("Enter email: ").strip()
                if not email:
                    print("Email cannot be empty")
                    continue
                if User.query.filter_by(email=email).first():
                    print("Email already exists. Please choose another.")
                    continue
                
                # Get password
                password = input("Enter password: ").strip()
                if not password:
                    print("Password cannot be empty")
                    continue
                
                # Get authorizer status
                is_authorizer = input("Make this user an authorizer? (y/n): ").lower().strip() == 'y'
                
                # Get role
                valid_roles = ['Bioinformatics', 'Cancer Team', 'Rare Disease Team']
                while True:
                    role = input(f"Enter role ({'/'.join(valid_roles)}): ").strip()
                    if role in valid_roles:
                        break
                    print(f"Invalid role. Please choose from: {', '.join(valid_roles)}")

                # Create new user
                new_user = User(
                    username=username,
                    email=email,
                    is_authorizer=is_authorizer,
                    role=role
                )
                new_user.set_password(password)
                
                # Add to database
                print("\nAttempting to create user...")
                db.session.add(new_user)
                db.session.commit()
                
                print("\nUser created successfully!")
                print(f"Username: {new_user.username}")
                print(f"User ID: {new_user.id}")
                print(f"Role: {new_user.role}")
                print(f"Authorizer status: {'Yes' if new_user.is_authorizer else 'No'}")
                break
                
            except IntegrityError as e:
                db.session.rollback()
                print(f"\nDatabase integrity error: {str(e)}")
                print("This might be due to a duplicate username or email.")
                continue
            except Exception as e:
                db.session.rollback()
                print(f"\nUnexpected error: {str(e)}")
                print("Error type:", type(e).__name__)
                continue

if __name__ == "__main__":
    create_auth_user()