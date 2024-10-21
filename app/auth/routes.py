"""
routes.py - Defines the authentication and user management routes for the application.

Routes:
- set_authorizer(user_id): Sets or removes authorizer status for a user.
- user_management(): Displays the user management page for authorizers.
- create_user(): Handles the creation of new users.
- login(): Manages user login.
- logout(): Handles user logout.
- settings(): Displays and updates application settings.
"""

from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import auth_bp
from app.models import User, Settings
from app import db
from .forms import SettingsForm

import json
import os

@auth_bp.route('/set_authorizer/<int:user_id>', methods=['POST'])
@login_required
def set_authorizer(user_id):
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
    if not current_user.is_authorizer:
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('bed_manager.index'))

    users = User.query.all()
    return render_template('auth/user_management.html', users=users)

@auth_bp.route('/create_user', methods=['POST'])
@login_required
def create_user():
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
    if current_user.is_authenticated:
        return redirect(url_for('bed_manager.index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash('Invalid username or password', 'error')
            return redirect(url_for('auth.login'))
        login_user(user, remember=True)
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('bed_manager.index')
        return redirect(next_page)
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('bed_manager.index'))

@auth_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    form = SettingsForm()
    if form.validate_on_submit():
        # Update or create settings in the database
        settings = Settings.query.first()
        if not settings:
            settings = Settings()
            db.session.add(settings)
        
        settings.data_padding = 0 if form.data_padding.data is None else form.data_padding.data
        settings.sambamba_padding = 0 if form.sambamba_padding.data is None else form.sambamba_padding.data
        settings.exomeDepth_padding = 0 if form.exomeDepth_padding.data is None else form.exomeDepth_padding.data
        settings.cnv_padding = 0 if form.cnv_padding.data is None else form.cnv_padding.data
        
        db.session.commit()

        # Update the JSON file
        json_file_path = os.path.join(current_app.root_path, '..', 'settings.json')
        with open(json_file_path, 'r+') as json_file:
            json_data = json.load(json_file)
            json_data['data_padding'] = settings.data_padding
            json_data['sambamba_padding'] = settings.sambamba_padding
            json_data['exomeDepth_padding'] = settings.exomeDepth_padding
            json_data['cnv_padding'] = settings.cnv_padding
            json_file.seek(0)
            json.dump(json_data, json_file, indent=4)
            json_file.truncate()

        flash('Settings updated successfully', 'success')
        return redirect(url_for('auth.settings'))
    
    # Pre-populate form with existing settings
    settings = Settings.query.first()
    if settings:
        form.data_padding.data = settings.data_padding
        form.sambamba_padding.data = settings.sambamba_padding
        form.exomeDepth_padding.data = settings.exomeDepth_padding
        form.cnv_padding.data = settings.cnv_padding
    
    return render_template('settings.html', form=form)
