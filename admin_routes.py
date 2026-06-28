# ----------------- routes/admin_routes.py -----------------

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from bson.objectid import ObjectId
from extensions import mongo, mail
from flask_mail import Message

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ----------------- Admin Dashboard -----------------
@admin_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'admin':
        flash('Unauthorized.')
        return redirect(url_for('main.index'))

    admin_user = mongo.db.users.find_one({'role': 'admin'})
    total_revenue = admin_user.get('total_revenue', 0) if admin_user else 0

    pending_doctors = list(mongo.db.users.find({'role': 'doctor', 'is_approved': False}))
    approved_doctors = list(mongo.db.users.find({'role': 'doctor', 'is_approved': True}))

    # ✅ Count unread
    unread_count = mongo.db.chats.count_documents({
        'receiver_id': str(current_user.id),
        'is_read': False
    })

    return render_template(
        'dashboard_admin.html',
        total_revenue=total_revenue,
        pending_doctors=pending_doctors,
        approved_doctors=approved_doctors,
        unread_count=unread_count
    )


# ----------------- Approve Doctor -----------------
@admin_bp.route('/approve_doctor/<doctor_id>')
@login_required
def approve_doctor(doctor_id):
    if current_user.role != 'admin':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    mongo.db.users.update_one({'_id': ObjectId(doctor_id)}, {'$set': {'is_approved': True}})

    doctor = mongo.db.users.find_one({'_id': ObjectId(doctor_id)})
    if doctor:
        msg = Message('Doctor Approval',
                      sender='your_email@gmail.com',
                      recipients=[doctor['email']])
        msg.body = 'Your account has been approved by the admin. You can now log in.'
        mail.send(msg)

    flash('Doctor approved and email sent.')
    return redirect(url_for('admin.dashboard'))


# ----------------- Reject Doctor -----------------
@admin_bp.route('/reject_doctor/<doctor_id>', methods=['GET', 'POST'])
@login_required
def reject_doctor(doctor_id):
    if current_user.role != 'admin':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    doctor = mongo.db.users.find_one({'_id': ObjectId(doctor_id)})

    if request.method == 'POST':
        reason = request.form['reason']
        mongo.db.users.delete_one({'_id': ObjectId(doctor_id)})

        msg = Message('Doctor Registration Rejected',
                      sender='your_email@gmail.com',
                      recipients=[doctor['email']])
        msg.body = f'Your registration was rejected. Reason: {reason}'
        mail.send(msg)

        flash('Doctor rejected and email sent.')
        return redirect(url_for('admin.dashboard'))

    return render_template('reject_doctor.html', doctor=doctor)


# ----------------- View Doctor Profile (Approved & Pending) -----------------
@admin_bp.route('/doctor_profile/<doctor_id>')
@login_required
def doctor_profile(doctor_id):
    if current_user.role != 'admin':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    doctor = mongo.db.users.find_one({'_id': ObjectId(doctor_id), 'role': 'doctor'})
    if not doctor:
        flash('Doctor not found.')
        return redirect(url_for('admin.dashboard'))

    average_rating = None
    reviews = []

    if doctor.get('is_approved'):
        ratings_cursor = mongo.db.appointments.find({
            'doctor_id': doctor_id,
            'rating': {'$exists': True},
            'review': {'$exists': True}
        })

        total = 0
        count = 0

        for r in ratings_cursor:
            if r.get('rating') is not None and r.get('review', '').strip() != '':
                total += r['rating']
                count += 1

                patient = mongo.db.users.find_one({'_id': ObjectId(r['patient_id'])})
                patient_name = patient.get('full_name', 'Unknown') if patient else "Unknown"

                reviews.append({
                    'rating': r['rating'],
                    'review': r['review'],
                    'patient_name': patient_name
                })

        average_rating = round(total / count, 2) if count > 0 else None

        return render_template(
            'admin_doctor_profile.html',
            doctor=doctor,
            average_rating=average_rating,
            reviews=reviews  # ✅ final name used in HTML
        )

    else:
        return render_template('pending_doctors_view_profile.html', doctor=doctor)

# ----------------- Unapprove Doctor -----------------
@admin_bp.route('/doctor/<doctor_id>/unapprove', methods=['GET', 'POST'])
@login_required
def unapprove_doctor(doctor_id):
    if current_user.role != 'admin':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    doctor = mongo.db.users.find_one({'_id': ObjectId(doctor_id), 'role': 'doctor'})
    if not doctor:
        flash('Doctor not found.')
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        reason = request.form.get('reason', '').strip()
        mongo.db.users.update_one({'_id': ObjectId(doctor_id)}, {'$set': {'is_approved': False}})

        if doctor.get('email'):
            msg = Message(
                'Your Doctor Account Status',
                sender='your_email@gmail.com',
                recipients=[doctor['email']]
            )
            msg.body = f"""Dear Dr. {doctor.get('full_name', 'Doctor')},

Your account status has been changed to *pending* by the admin.
Reason: {reason or 'No reason provided.'}

Please wait for re-approval.

Regards,
Team"""
            mail.send(msg)

        flash(f"Doctor {doctor.get('full_name', doctor.get('email'))} has been unapproved and notified.")
        return redirect(url_for('admin.dashboard'))

    return render_template('unapprove_doctor.html', doctor=doctor)

# ----------------- Appointments -----------------
@admin_bp.route('/appointments')
@login_required
def appointments():
    if current_user.role != 'admin':
        flash('Unauthorized.')
        return redirect(url_for('main.index'))

    appointments = []
    for appt in mongo.db.appointments.find():
        patient = mongo.db.users.find_one({'_id': ObjectId(appt['patient_id'])})
        doctor = mongo.db.users.find_one({'_id': ObjectId(appt['doctor_id'])})
        appt['patient_name'] = patient['full_name'] if patient else 'Unknown'
        appt['doctor_name'] = doctor['full_name'] if doctor else 'Unknown'
        appointments.append(appt)

    # ✅ Sort appointments by date + slot_time in descending order (newest first)
    from datetime import datetime

    def get_appt_datetime(appt):
        try:
            # You can adjust the format if needed
            dt_str = f"{appt.get('date', '')} {appt.get('slot_time', '00:00')}"
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        except:
            return datetime.min  # fallback for broken date/time

    appointments.sort(key=get_appt_datetime, reverse=True)

    return render_template('admin_appointments.html', appointments=appointments)


# ------------------ View All Patients ------------------
@admin_bp.route('/patients')
@login_required
def patients():
    if current_user.role != 'admin':
        flash('Unauthorized.')
        return redirect(url_for('main.index'))

    patients = list(mongo.db.users.find({'role': 'patient'}))
    return render_template('admin_patients.html', patients=patients)


# ------------------ Delete Patients with Reason ------------------
@admin_bp.route('/delete_patient/<patient_id>', methods=['GET', 'POST'])
@login_required
def delete_patient(patient_id):
    if current_user.role != 'admin':
        flash('Unauthorized.')
        return redirect(url_for('main.index'))

    patient = mongo.db.users.find_one({'_id': ObjectId(patient_id), 'role': 'patient'})
    if not patient:
        flash('Patient not found.')
        return redirect(url_for('admin.patients'))

    if request.method == 'POST':
        reason = request.form['reason']
        mongo.db.users.delete_one({'_id': ObjectId(patient_id)})

        msg = Message(
            'Your Account Deleted',
            sender='your_email@gmail.com',
            recipients=[patient['email']]
        )
        msg.body = f"Dear {patient['full_name']},\n\nYour account has been deleted by admin for the following reason:\n{reason}\n\nRegards,\nTeam"
        mail.send(msg)

        flash('Patient deleted and email sent.')
        return redirect(url_for('admin.patients'))

    return render_template('admin_delete_patient.html', patient=patient)