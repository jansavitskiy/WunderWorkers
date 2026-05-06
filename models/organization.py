from datetime import datetime
from models.db import db


class Organization(db.Model):
    __tablename__ = 'organizations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    inn = db.Column(db.String(12), nullable=True, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    reports = db.relationship('Report', back_populates='organization', lazy=True)
