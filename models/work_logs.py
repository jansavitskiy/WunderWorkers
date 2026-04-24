from models.db import db

class WorkLog(db.Model):
    __tablename__ = 'work_logs'
    id = db.Column(db.Integer, primary_key=True)
    # ... поля