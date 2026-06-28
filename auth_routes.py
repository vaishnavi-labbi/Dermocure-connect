# routes/auth_routes.py

from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from extensions import mongo, login_manager, mail
from models.user_model import User
import random
from flask_mail import Message
from bson.objectid import ObjectId

auth_bp = Blueprint('auth', __name__)

@login_manager.user_loader
def load_user(user_id):
    user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
    return User(user_data) if user_data else None

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')

        # Always use +91 for country code
        phone_number = request.form.get('phone_number').strip()
        country_code = '+91'
        full_whatsapp_number = f"{country_code}{phone_number}"

        hashed_password = generate_password_hash(password)

        existing_user = mongo.db.users.find_one({'email': email})
        if existing_user:
            flash('Email already registered!')
            return redirect(url_for('auth.register'))

        user_data = {
            'full_name': full_name,
            'email': email,
            'password': hashed_password,
            'role': role,
            'whatsapp_number': full_whatsapp_number,
            'is_approved': False if role == 'doctor' else True,
        }

        if role == 'doctor':
            specialization = request.form.get('specialization')
            about = request.form.get('about')
            hospital_name = request.form.get('hospital_name')
            hospital_code = request.form.get('hospital_code')
            doctor_code = request.form.get('doctor_code')
            address = request.form.get('address')
            education = request.form.get('education')
            city = request.form.get('city')

            user_data.update({
                'specialization': specialization,
                'about': about,
                'hospital_name': hospital_name,
                'hospital_code': hospital_code,
                'doctor_code': doctor_code,
                'address': address,
                'education': education,
                'city': city,
                'slots': []
            })

        mongo.db.users.insert_one(user_data)

        # ✅ Send confirmation or pending approval email
        if role == 'doctor':
            msg = Message(
                'Registration Received - Pending Approval',
                sender='your_email@gmail.com',
                recipients=[email]
            )
            msg.body = (
                f"Dear Dr. {full_name},\n\n"
                "Thank you for registering on our Doctor Appointment System.\n"
                "Your account is pending admin approval. "
                "You will receive an email once your account is approved.\n\n"
                "Regards,\nTeam"
            )
            flash('Registration successful! Please wait for admin approval.')
        else:
            msg = Message(
                'Registration Successful',
                sender='your_email@gmail.com',
                recipients=[email]
            )
            msg.body = (
                f"Dear {full_name},\n\n"
                "Thank you for registering on our Doctor Appointment System.\n"
                "You can now login and start booking appointments!\n\n"
                "Regards,\nTeam"
            )
            flash('Registration successful! Please login.')

        mail.send(msg)

        return redirect(url_for('auth.login'))

    return render_template('register.html')

# ------------------ LOGIN ------------------
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user_data = mongo.db.users.find_one({'email': email})
        if not user_data or not check_password_hash(user_data['password'], password):
            flash('Invalid credentials')
            return redirect(url_for('auth.login'))

        if user_data['role'] == 'doctor' and not user_data.get('is_approved', False):
            flash('Doctor account not approved by admin yet.')
            return redirect(url_for('auth.login'))

        user = User(user_data)
        login_user(user)
        flash('Logged in successfully')

        if user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif user.role == 'doctor':
            return redirect(url_for('doctor.dashboard'))
        elif user.role == 'patient':
            return redirect(url_for('patient.dashboard'))
        else:
            return redirect(url_for('main.index'))

    return render_template('login.html')

# ------------------ LOGOUT ------------------
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.')
    return redirect(url_for('main.index'))

# ------------------ FORGOT PASSWORD: Send OTP ------------------
@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = mongo.db.users.find_one({'email': email})
        if user:
            otp = random.randint(100000, 999999)
            session['reset_otp'] = otp
            session['reset_email'] = email

            msg = Message('Password Reset OTP',
                          sender='your_email@gmail.com',
                          recipients=[email])
            msg.body = f'Your OTP for password reset is: {otp}'
            mail.send(msg)

            flash('OTP sent to your email.')
            return redirect(url_for('auth.reset_password'))
        else:
            flash('Email not found.')
    return render_template('forgot_password.html')

# ------------------ RESET PASSWORD WITH OTP ------------------
@auth_bp.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        otp_entered = request.form['otp']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if new_password != confirm_password:
            flash('Passwords do not match.')
            return redirect(url_for('auth.reset_password'))

        if int(otp_entered) == int(session.get('reset_otp')):
            email = session.get('reset_email')
            hashed_password = generate_password_hash(new_password)
            mongo.db.users.update_one({'email': email}, {'$set': {'password': hashed_password}})
            session.pop('reset_otp', None)
            session.pop('reset_email', None)
            flash('Password reset successful. Please login.')
            return redirect(url_for('auth.login'))
        else:
            flash('Invalid OTP.')
    return render_template('reset_password.html')

# ------------------ CHANGE PASSWORD ------------------
@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        user = mongo.db.users.find_one({'_id': ObjectId(current_user.id)})

        if not check_password_hash(user['password'], current_password):
            flash('Current password is incorrect.')
            return redirect(url_for('auth.change_password'))

        if new_password != confirm_password:
            flash('New passwords do not match.')
            return redirect(url_for('auth.change_password'))

        hashed_password = generate_password_hash(new_password)

        # ✅ Correct usage with ObjectId
        mongo.db.users.update_one(
            {'_id': ObjectId(current_user.id)},
            {'$set': {'password': hashed_password}}
        )

        flash('Password changed successfully!')
        return redirect(url_for('main.index'))

    return render_template('change_password.html')