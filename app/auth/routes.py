"""
routes.py - Defines the authentication and user management routes for the application.

Routes:
- set_authorizer(user_id): Sets or removes authorizer status for a user.
- user_management(): Displays the user management page for authorizers.
- create_user(): Handles the creation of new users.
- login(): Manages user login.
- logout(): Handles user logout.
- register(): Handles user registration.
"""

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import auth_bp
from app.models import User, Settings
from app import db
from urllib.parse import urlparse
from app.auth.forms import LoginForm, RegistrationForm

@auth_bp.route('/set_authorizer/<int:user_id>', methods=['POST'])
@login_required
def set_authorizer(user_id):
    """
    Sets or removes the authorizer status for a user.

    Args:
        user_id (int): The ID of the user to update.

    Returns:
        Redirects to the user management page.
    """
    if not current_user.is_authorizer:
        flash('You do not have permission to perform this action.', 'error')
        return redirect(url_for('auth.user_management'))

    user = User.query.get_or_404(user_id)
    is_authorizer = request.form.get('is_authorizer') == 'true'

    user.is_authorizer = is_authorizer
    db.session.commit()

    action = 'set' if is_authorizer else 'removed'
    flash(f"User {user.username}'s authorizer status has been {action}.", 'success')
    return redirect(url_for('auth.user_management'))

@auth_bp.route('/user_management')
@login_required
def user_management():
    """
    Displays the user management page for authorizers.

    Returns:
        Renders the user management template with a list of users.
    """
    if not current_user.is_authorizer:
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('bed_manager.index'))

    users = User.query.all()
    return render_template('auth/user_management.html', users=users)

@auth_bp.route('/create_user', methods=['POST'])
@login_required
def create_user():
    """
    Handles the creation of new users.

    Returns:
        Redirects to the user management page.
    """
    if not current_user.is_authorizer:
        flash('You do not have permission to create users.', 'error')
        return redirect(url_for('auth.user_management'))

    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    is_authorizer = 'is_authorizer' in request.form
    role = request.form.get('role')

    if User.query.filter_by(username=username).first():
        flash('Username already exists.', 'error')
        return redirect(url_for('auth.user_management'))

    if User.query.filter_by(email=email).first():
        flash('Email already exists.', 'error')
        return redirect(url_for('auth.user_management'))

    new_user = User(username=username, email=email, is_authorizer=is_authorizer, role=role)
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.commit()

    flash(f'User {username} has been created successfully.', 'success')
    return redirect(url_for('auth.user_management'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Manages user login.

    Returns:
        Renders the login template or redirects to the next page.
    """
    if current_user.is_authenticated:
        return redirect(url_for('bed_generator.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('auth.login'))
        login_user(user)
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('bed_generator.index')
        return redirect(next_page)
    return render_template('auth/login.html', title='Sign In', form=form)

@auth_bp.route('/logout')
def logout():
    """
    Handles user logout.

    Returns:
        Redirects to the index page.
    """
    logout_user()
    return redirect(url_for('bed_generator.index'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    Handles user registration.

    Returns:
        Renders the registration template or redirects to the login page.
    """
    if current_user.is_authenticated:
        return redirect(url_for('bed_generator.index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now a registered user!', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', title='Register', form=form)