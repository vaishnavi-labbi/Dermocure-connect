# routes/patient_routes.py

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from bson.objectid import ObjectId
from extensions import mongo
from datetime import datetime

patient_bp = Blueprint('patient', __name__, url_prefix='/patient')

@patient_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'patient':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    search_query = request.args.get('search_query', '').strip()
    query = {'role': 'doctor', 'is_approved': True}

    if search_query:
        query['$or'] = [
            {'full_name': {'$regex': search_query, '$options': 'i'}},
            {'specialization': {'$regex': search_query, '$options': 'i'}}
        ]

    doctors = mongo.db.users.find(query)

    appointments = []
    raw_appointments = mongo.db.appointments.find({'patient_id': current_user.id})
    for appt in raw_appointments:
        doctor = mongo.db.users.find_one({'_id': ObjectId(appt['doctor_id'])})
        appt['doctor_name'] = doctor.get('full_name', 'Unknown Doctor') if doctor else 'Unknown Doctor'
        appt['doctor_whatsapp'] = doctor.get('whatsapp_number', '') if doctor else ''
        appointments.append(appt)

    return render_template('dashboard_patient.html',
                           doctors=doctors,
                           appointments=appointments)

@patient_bp.route('/doctor/<doctor_id>')
@login_required
def doctor_profile(doctor_id):
    if current_user.role != 'patient':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    doctor = mongo.db.users.find_one({'_id': ObjectId(doctor_id)})

    slots = mongo.db.slots.find({
        'doctor_id': doctor_id,
        'is_booked': False
    })

    completed_appts = list(mongo.db.appointments.find({
        'doctor_id': str(doctor_id),
        'status': 'completed',
        'rating': {'$exists': True}
    }))

    doctor_reviews = []
    if completed_appts:
        ratings = []
        for appt in completed_appts:
            if 'rating' in appt and appt['rating'] is not None:
                ratings.append(appt['rating'])
                patient = mongo.db.users.find_one({'_id': ObjectId(appt['patient_id'])})
                doctor_reviews.append({
                    'rating': appt['rating'],
                    'review': appt.get('review', ''),
                    'patient_name': patient.get('full_name', 'Unknown') if patient else 'Unknown'
                })
        average_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
    else:
        average_rating = None

    return render_template(
        'view_doctor.html',
        doctor=doctor,
        slots=slots,
        average_rating=average_rating,
        doctor_reviews=doctor_reviews  # Pass the reviews to template
    )

@patient_bp.route('/book/<slot_id>', methods=['GET', 'POST'])
@login_required
def book_slot(slot_id):
    if current_user.role != 'patient':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    slot = mongo.db.slots.find_one({'_id': ObjectId(slot_id)})
    if not slot or slot['is_booked']:
        flash('Slot not available.')
        return redirect(url_for('patient.dashboard'))

    if request.method == 'POST':
        payment_amount = 500
        doctor_share = int(payment_amount * 0.90)
        admin_share = payment_amount - doctor_share

        mongo.db.slots.update_one({'_id': ObjectId(slot_id)}, {'$set': {'is_booked': True}})

        appointment = {
            'patient_id': current_user.id,
            'doctor_id': slot['doctor_id'],
            'slot_id': slot_id,
            'date': slot['date'],
            'slot_time': slot['time'],
            'status': 'pending',
            'payment_amount': payment_amount,
            'doctor_share': doctor_share,
            'admin_share': admin_share,
            'report_file': None,
            'rating': None,
            'created_at': datetime.utcnow()
        }

        mongo.db.appointments.insert_one(appointment)

        flash('Appointment booked! Pending doctor approval.')
        return redirect(url_for('patient.dashboard'))

    return render_template('book_slot.html', slot=slot)

@patient_bp.route('/upload_report/<appointment_id>', methods=['GET', 'POST'])
@login_required
def upload_report(appointment_id):
    if current_user.role != 'patient':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        report_file = request.files['report']
        filename = report_file.filename
        report_file.save(f'static/uploads/{filename}')

        mongo.db.appointments.update_one(
            {'_id': ObjectId(appointment_id)},
            {'$set': {'patient_report_file': filename}}
        )
        flash('Report uploaded.')
        return redirect(url_for('patient.dashboard'))

    return render_template('upload_report.html', appointment_id=appointment_id)

@patient_bp.route('/rate_doctor/<appointment_id>', methods=['GET', 'POST'])
@login_required
def rate_doctor(appointment_id):
    if current_user.role != 'patient':
        flash('Unauthorized.')
        return redirect(url_for('main.index'))

    appointment = mongo.db.appointments.find_one({'_id': ObjectId(appointment_id)})

    if not appointment or appointment.get('patient_id') != current_user.id:
        flash('Appointment not found or access denied.')
        return redirect(url_for('patient.dashboard'))

    if request.method == 'POST':
        rating = int(request.form['rating'])
        review = request.form.get('review', '').strip()

        mongo.db.appointments.update_one(
            {'_id': ObjectId(appointment_id)},
            {'$set': {'rating': rating, 'review': review}}
        )
        flash('Thanks for your feedback!')
        return redirect(url_for('patient.dashboard'))

    return render_template('rate_doctor.html', appointment=appointment)

@patient_bp.route('/payment/<slot_id>', methods=['GET', 'POST'])
@login_required
def payment(slot_id):
    slot = mongo.db.slots.find_one({'_id': ObjectId(slot_id)})

    if not slot or slot['is_booked']:
        flash('Slot not available.')
        return redirect(url_for('patient.dashboard'))

    if request.method == 'POST':
        appointment = {
            'patient_id': str(current_user.id),
            'doctor_id': slot['doctor_id'],
            'slot_id': str(slot['_id']),
            'date': slot['date'],
            'slot_time': slot['time'],
            'status': 'pending',
            'payment_amount': 500,
            'doctor_share': 450,
            'admin_share': 50
        }

        mongo.db.appointments.insert_one(appointment)
        mongo.db.slots.update_one({'_id': ObjectId(slot_id)}, {'$set': {'is_booked': True}})
        flash('Payment successful! Appointment booked.')
        return redirect(url_for('patient.dashboard'))

    return render_template('payment.html', slot=slot)

from datetime import datetime
from bson import ObjectId

@patient_bp.route('/history')
@login_required
def view_history():
    if current_user.role != 'patient':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    # Get all appointments for the patient
    raw_appointments = mongo.db.appointments.find({'patient_id': current_user.id})

    completed = []
    rejected = []

    for appt in raw_appointments:
        doctor = mongo.db.users.find_one({'_id': ObjectId(appt['doctor_id'])})
        appt['doctor_name'] = doctor.get('full_name', 'Unknown Doctor') if doctor else 'Unknown Doctor'

        if appt.get('status') == 'completed':
            completed.append(appt)
        elif appt.get('status') == 'rejected':
            rejected.append(appt)

    # ✅ Sort each list by date DESC, then slot_time DESC
    def sort_key(appt):
        # Combine date and time for sorting
        slot_datetime_str = f"{appt.get('date', '')} {appt.get('slot_time', '')}"
        try:
            slot_datetime = datetime.strptime(slot_datetime_str, "%Y-%m-%d %H:%M")
        except ValueError:
            slot_datetime = datetime.min  # fallback for bad data
        return slot_datetime

    completed = sorted(completed, key=sort_key, reverse=True)
    rejected = sorted(rejected, key=sort_key, reverse=True)

    return render_template('view_history.html', completed=completed, rejected=rejected)

@patient_bp.route('/doctors')
@login_required
def view_doctors():
    if current_user.role != 'patient':
        flash('Unauthorized access.')
        return redirect(url_for('main.index'))

    search_query = request.args.get('search_query', '').strip()
    query = {'role': 'doctor', 'is_approved': True}

    if search_query:
        query['$or'] = [
            {'full_name': {'$regex': search_query, '$options': 'i'}},
            {'specialization': {'$regex': search_query, '$options': 'i'}}
        ]

    doctors = mongo.db.users.find(query)

    return render_template('patient_doctors.html',
                           doctors=doctors,
                           search_query=search_query)