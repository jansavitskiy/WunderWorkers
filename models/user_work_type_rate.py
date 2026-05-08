from models.db import db


class UserWorkTypeRate(db.Model):
    __tablename__ = 'user_work_type_rates'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    work_type_id = db.Column(db.Integer, db.ForeignKey('work_types.id'), nullable=False)
    rate_per_hour = db.Column(db.Float, nullable=False, default=0.0)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'work_type_id', name='uq_user_work_type'),
    )

    user = db.relationship('User', backref='work_type_rates')
    work_type = db.relationship('WorkType', backref='user_rates')
