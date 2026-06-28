# routes/doctor_routes.py

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from bson.objectid import ObjectId
from extensions import mongo, mail
from flask_mail import Message
from datetime import datetime

doctor_bp = Blueprint('doctor', __name__, url_prefix='/doctor')

# ✅ Doctor Dashboard Route
# ✅ Doctor Dashboard Route
@doctor_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'doctor':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    total_revenue = sum(
        appt['doctor_share'] for appt in mongo.db.appointments.find({
            'doctor_id': current_user.id,
            'status': 'completed'
        })
    )

    slots = list(mongo.db.slots.find({'doctor_id': current_user.id}))

    pending_appointments = []
    ongoing_appointments = []
    completed_appointments = []

    raw_appointments = mongo.db.appointments.find({'doctor_id': current_user.id})
    for appt in raw_appointments:
        patient = mongo.db.users.find_one({'_id': ObjectId(appt['patient_id'])})
        appt['patient_name'] = patient.get('full_name', 'Unknown Patient') if patient else 'Unknown Patient'
        appt['patient_whatsapp'] = patient.get('whatsapp_number', '') if patient else ''

        if appt['status'] == 'pending':
            pending_appointments.append(appt)
        elif appt['status'] == 'approved':
            ongoing_appointments.append(appt)
        elif appt['status'] == 'completed':
            completed_appointments.append(appt)

    admin = mongo.db.users.find_one({'role': 'admin'})
    admin_id = str(admin['_id']) if admin else ''

    admin_unread_count = mongo.db.chats.count_documents({
        'sender_id': admin_id,
        'receiver_id': str(current_user.id),
        'is_read': False
    })

    return render_template(
        'dashboard_doctor.html',
        total_revenue=total_revenue,
        slots=slots,
        pending_appointments=pending_appointments,
        ongoing_appointments=ongoing_appointments,
        completed_appointments=completed_appointments,
        admin_id=admin_id,
        admin_unread_count=admin_unread_count
    )

from datetime import datetime

@doctor_bp.route('/add_slot', methods=['GET', 'POST'])
@login_required
def add_slot():
    if current_user.role != 'doctor':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        date = request.form['date']
        time = request.form['time']

        # Combine date and time into a single datetime object
        try:
            slot_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        except ValueError:
            flash('Invalid date or time format.')
            return redirect(url_for('doctor.add_slot'))

        now = datetime.now()

        # Validate that the slot is not in the past
        if slot_datetime < now:
            flash('Cannot add a slot in the past. Please choose a valid date and time.')
            return redirect(url_for('doctor.add_slot'))

        mongo.db.slots.insert_one({
            'doctor_id': current_user.id,
            'date': date,
            'time': time,
            'is_booked': False
        })

        flash('Slot added successfully.')
        return redirect(url_for('doctor.dashboard'))

    return render_template('add_slot.html')

@doctor_bp.route('/delete_slot/<slot_id>', methods=['POST'])
@login_required
def delete_slot(slot_id):
    if current_user.role != 'doctor':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    mongo.db.slots.delete_one({
        '_id': ObjectId(slot_id),
        'doctor_id': str(current_user.id),
        'is_booked': False  # ✅ Only allows deleting slots that are NOT booked!
    })

    flash('Slot deleted successfully!')
    return redirect(url_for('doctor.dashboard'))

@doctor_bp.route('/approve_appointment/<appointment_id>')
@login_required
def approve_appointment(appointment_id):
    if current_user.role != 'doctor':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    mongo.db.appointments.update_one({'_id': ObjectId(appointment_id)},
                                     {'$set': {'status': 'approved'}})

    appointment = mongo.db.appointments.find_one({'_id': ObjectId(appointment_id)})
    mongo.db.slots.update_one({'_id': ObjectId(appointment['slot_id'])},
                              {'$set': {'is_booked': True}})

    # ✅ Pull doctor full name from DB
    doctor = mongo.db.users.find_one({'_id': ObjectId(current_user.id)})
    doctor_name = doctor.get('full_name', 'Your Doctor')

    # ✅ Send approval email to patient
    patient = mongo.db.users.find_one({'_id': ObjectId(appointment['patient_id'])})
    if patient:
        msg = Message(
            'Your Appointment Approved!',
            sender='your_email@gmail.com',
            recipients=[patient['email']]
        )
        msg.body = (
            f"Dear {patient['full_name']},\n\n"
            f"Your appointment with Dr. {doctor_name} "
            f"on {appointment['date']} at {appointment['slot_time']} has been approved.\n\n"
            "Thank you for using our Doctor Appointment System!\n\n"
            "Regards,\nTeam"
        )
        mail.send(msg)

    flash('Appointment approved and email sent to patient.')
    return redirect(url_for('doctor.dashboard'))

@doctor_bp.route('/reject_appointment/<appointment_id>', methods=['GET', 'POST'])
@login_required
def reject_appointment(appointment_id):
    if current_user.role != 'doctor':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    appointment = mongo.db.appointments.find_one({'_id': ObjectId(appointment_id)})

    if request.method == 'POST':
        reason = request.form['reason']

        mongo.db.appointments.update_one(
            {'_id': ObjectId(appointment_id)},
            {'$set': {'status': 'rejected', 'reject_reason': reason}}
        )
        mongo.db.slots.update_one({'_id': ObjectId(appointment['slot_id'])},
                                  {'$set': {'is_booked': False}})

        patient = mongo.db.users.find_one({'_id': ObjectId(appointment['patient_id'])})
        if patient:
            msg = Message('Appointment Rejected',
                          sender='your_email@gmail.com',
                          recipients=[patient['email']])
            msg.body = f'Your appointment was rejected. Reason: {reason}'
            mail.send(msg)

        flash('Appointment rejected and email sent.')
        return redirect(url_for('doctor.dashboard'))

    return render_template('reject_appointment_doctor.html', appointment=appointment)

@doctor_bp.route('/complete_appointment/<appointment_id>')
@login_required
def complete_appointment(appointment_id):
    if current_user.role != 'doctor':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    appointment = mongo.db.appointments.find_one({'_id': ObjectId(appointment_id)})

    mongo.db.appointments.update_one({'_id': ObjectId(appointment_id)},
                                     {'$set': {'status': 'completed'}})

    mongo.db.users.update_one(
        {'_id': ObjectId(current_user.id)},
        {'$inc': {'total_revenue': appointment['doctor_share']}}
    )

    admin_user = mongo.db.users.find_one({'role': 'admin'})
    if admin_user:
        mongo.db.users.update_one(
            {'_id': admin_user['_id']},
            {'$inc': {'total_revenue': appointment['admin_share']}}
        )

    # ✅ Send email to patient when appointment marked as completed
    patient = mongo.db.users.find_one({'_id': ObjectId(appointment['patient_id'])})
    if patient:
        doctor_data = mongo.db.users.find_one({'_id': ObjectId(current_user.id)})
        doctor_name = doctor_data.get('full_name', 'Doctor')

        msg = Message(
            'Appointment Completed',
            sender='your_email@gmail.com',
            recipients=[patient['email']]
        )
        msg.body = (
            f"Hello {patient.get('full_name', 'Patient')},\n\n"
            f"Your appointment with Dr. {doctor_name} "
            f"on {appointment['date']} at {appointment['slot_time']} has been marked as completed.\n\n"
            f"Thank you for using our Doctor Appointment System!"
        )
        mail.send(msg)

    flash('Appointment marked as completed, revenue updated & patient notified by email.')
    return redirect(url_for('doctor.dashboard'))

@doctor_bp.route('/upload_report/<appointment_id>', methods=['GET', 'POST'])
@login_required
def upload_report(appointment_id):
    if current_user.role != 'doctor':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        report_file = request.files['report']
        filename = report_file.filename
        report_file.save(f'static/uploads/{filename}')

        mongo.db.appointments.update_one(
            {'_id': ObjectId(appointment_id)},
            {'$set': {'doctor_report_file': filename}}
        )
        flash('Report uploaded.')
        return redirect(url_for('doctor.dashboard'))

    return render_template('upload_report.html', appointment_id=appointment_id)

@doctor_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if current_user.role != 'doctor':
        flash('Unauthorized.')
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        full_name = request.form['full_name']
        specialization = request.form['specialization']
        about = request.form['about']

        # ✅ NEW FIELDS
        whatsapp_number = request.form.get('whatsapp_number')
        hospital_name = request.form.get('hospital_name')
        hospital_code = request.form.get('hospital_code')
        doctor_code = request.form.get('doctor_code')
        address = request.form.get('address')
        city = request.form.get('city')
        education = request.form.get('education')

        update_data = {
            'full_name': full_name,
            'specialization': specialization,
            'about': about,
            'whatsapp_number': whatsapp_number,
            'hospital_name': hospital_name,
            'hospital_code': hospital_code,
            'doctor_code': doctor_code,
            'address': address,
            'city': city,
            'education': education
        }

        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename != '':
                filename = file.filename
                file.save(f'static/uploads/{filename}')
                update_data['profile_pic'] = filename

        mongo.db.users.update_one(
            {'_id': ObjectId(current_user.id)},
            {'$set': update_data}
        )

        flash('Profile updated successfully!')
        return redirect(url_for('doctor.profile'))

    doctor = mongo.db.users.find_one({'_id': ObjectId(current_user.id)})

    completed_appts = list(mongo.db.appointments.find({
        'doctor_id': str(current_user.id),
        'status': 'completed',
        'rating': {'$exists': True}
    }))

    if completed_appts:
        ratings = [appt['rating'] for appt in completed_appts if 'rating' in appt and appt['rating'] is not None]
        average_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
    else:
        average_rating = None

    return render_template(
        'doctor_profile_dashboard.html',
        doctor=doctor,
        average_rating=average_rating
    )

from datetime import datetime
from bson import ObjectId

@doctor_bp.route('/history')
@login_required
def view_history():
    if current_user.role != 'doctor':
        flash('Unauthorized.')
        return redirect(url_for('main.index'))

    search_query = request.args.get('q', '').strip().lower()

    history_cursor = mongo.db.appointments.find({
        'doctor_id': current_user.id,
        'status': {'$in': ['completed', 'rejected']}
    })

    history = []
    for appt in history_cursor:
        patient = mongo.db.users.find_one({'_id': ObjectId(appt['patient_id'])})
        patient_name = patient.get('full_name', 'Unknown Patient') if patient else 'Unknown Patient'
        appt['patient_name'] = patient_name

        if not search_query or search_query in patient_name.lower():
            history.append(appt)

    # ✅ Sort by date and slot_time descending
    def sort_key(appt):
        slot_datetime_str = f"{appt.get('date', '')} {appt.get('slot_time', '')}"
        try:
            slot_datetime = datetime.strptime(slot_datetime_str, "%Y-%m-%d %H:%M")
        except ValueError:
            slot_datetime = datetime.min  # fallback if format is bad
        return slot_datetime

    history = sorted(history, key=sort_key, reverse=True)

    return render_template('doctor_history.html', history=history, search_query=search_query)

# ✅ Doctor view to list all admins for chat
@doctor_bp.route('/chat')
@login_required
def chat_admins():
    if current_user.role != 'doctor':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    admins = mongo.db.users.find({'role': 'admin'})
    return render_template('chat_admins_doctor.html', admins=admins)

# Add Prescription Route
@doctor_bp.route('/add_prescription/<appointment_id>', methods=['POST'])
@login_required
def add_prescription(appointment_id):
    if current_user.role != 'doctor':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    appointment = mongo.db.appointments.find_one({'_id': ObjectId(appointment_id)})

    if appointment is None:
        flash('Appointment not found.')
        return redirect(url_for('doctor.dashboard'))

    if 'doctor_prescription' in appointment and appointment['doctor_prescription'].strip():
        flash('Prescription already added. You cannot edit it.')
        return redirect(url_for('doctor.dashboard'))

    prescription = request.form.get('prescription').strip()
    
    if len(prescription.split()) > 100:
        flash('Prescription should not exceed 100 words.')
        return redirect(url_for('doctor.dashboard'))

    mongo.db.appointments.update_one(
        {'_id': ObjectId(appointment_id)},
        {'$set': {'doctor_prescription': prescription}}
    )

    flash('Prescription saved successfully!')
    return redirect(url_for('doctor.dashboard'))
