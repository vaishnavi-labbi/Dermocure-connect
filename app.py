# app.py
from flask import Flask
from config import Config
from extensions import mongo, login_manager, mail, socketio  # ✅ use same socketio
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)

# ✅ Initialize extensions
mongo.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.init_app(app)
mail.init_app(app)
socketio.init_app(app)  # ✅ bind to app

# ✅ Register blueprints
from routes.auth_routes import auth_bp
from routes.admin_routes import admin_bp
from routes.doctor_routes import doctor_bp
from routes.patient_routes import patient_bp
from routes.main_routes import main_bp
from routes.chat_routes import chat_bp

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(doctor_bp)
app.register_blueprint(patient_bp)
app.register_blueprint(main_bp)
app.register_blueprint(chat_bp)

if __name__ == '__main__':
    socketio.run(app, debug=True)  # ✅ Use socketio.run not app.run!
