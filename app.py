import io
import csv
import pytz
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from models.db import db, bcrypt
from models import User, Organization, WorkType
from datetime import datetime
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, TextAreaField, SubmitField, HiddenField, SelectField
from wtforms.validators import DataRequired, NumberRange, Optional
from sqlalchemy import inspect, text
from sqlalchemy.orm import joinedload

UTC = pytz.UTC
MSK = pytz.timezone('Europe/Moscow')

app = Flask(__name__)
app.secret_key = 'секретный-ключ-смени-его'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workers.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_ENABLED'] = True

app.jinja_env.filters['msk'] = lambda dt: msk_strftime(dt)

db.init_app(app)
bcrypt.init_app(app)


# Модель отчёта сотрудника
class Report(db.Model):
    __tablename__ = 'report'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    work_type_id = db.Column(db.Integer, db.ForeignKey('work_types.id'), nullable=True)
    hours_worked = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=False)
    work_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    date_created = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref=db.backref('reports', lazy=True))
    organization = db.relationship('Organization', back_populates='reports')
    work_type = db.relationship('WorkType', backref='reports')


# ── Формы ──────────────────────────────────────────────────────────────────────

class ReportForm(FlaskForm):
    organization = StringField('Название организации', validators=[DataRequired()])
    work_type_id = SelectField('Тип работы', coerce=int, validators=[DataRequired()])
    hours_worked = FloatField(
        'Время работы (часы)',
        validators=[
            DataRequired(),
            NumberRange(min=0.01, message='Время работы должно быть больше 0')
        ]
    )
    description = TextAreaField('Что выполнено', validators=[DataRequired()])
    submit = SubmitField('Добавить отчёт')


class AddOrganizationForm(FlaskForm):
    name = StringField('Название', validators=[DataRequired()])
    inn = StringField('ИНН', validators=[Optional()])
    submit = SubmitField('Добавить организацию')


class DeleteOrganizationForm(FlaskForm):
    org_id = HiddenField(validators=[DataRequired()])


class DeleteReportForm(FlaskForm):
    report_id = HiddenField(validators=[DataRequired()])


class AddWorkTypeForm(FlaskForm):
    name = StringField('Название', validators=[DataRequired()])
    description = TextAreaField('Описание', validators=[Optional()])
    submit = SubmitField('Добавить тип работы')


class EditWorkTypeForm(FlaskForm):
    pass


class WorkTypeActionForm(FlaskForm):
    wt_id = HiddenField(validators=[DataRequired()])


# ── Вспомогательные функции ─────────────────────────────────────────────────────

def to_msk(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = UTC.localize(dt)
    return dt.astimezone(MSK)


def msk_strftime(dt, format='%d.%m.%Y %H:%M'):
    msk_dt = to_msk(dt)
    return msk_dt.strftime(format) if msk_dt else ''


# ── Миграции ────────────────────────────────────────────────────────────────────

def migrate_reports_organization_fk():
    """Переносит старое текстовое поле organization → organization_id FK."""
    db.create_all()
    insp = inspect(db.engine)
    report_table = Report.__tablename__
    if report_table not in insp.get_table_names():
        return

    cols = {c['name'] for c in insp.get_columns(report_table)}
    if 'organization_id' not in cols:
        with db.engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE {report_table} ADD COLUMN organization_id INTEGER'))

    insp = inspect(db.engine)
    cols = {c['name'] for c in insp.get_columns(report_table)}
    if 'organization' not in cols:
        return

    rows = db.session.execute(
        text(
            f'SELECT id, organization FROM {report_table} WHERE organization_id IS NULL '
            f"AND organization IS NOT NULL AND organization != ''"
        )
    ).fetchall()

    for rid, org_name in rows:
        name = (org_name or '').strip()
        if not name:
            continue
        org = Organization.query.filter_by(name=name).first()
        if not org:
            org = Organization(name=name)
            db.session.add(org)
            db.session.flush()
        db.session.execute(
            text(f'UPDATE {report_table} SET organization_id = :oid WHERE id = :rid'),
            {'oid': org.id, 'rid': rid},
        )
    db.session.commit()

    insp = inspect(db.engine)
    cols = {c['name'] for c in insp.get_columns(report_table)}
    if 'organization' not in cols:
        return

    tmp = '_report_migrate_tmp'
    with db.engine.begin() as conn:
        conn.execute(
            text(
                f'CREATE TABLE IF NOT EXISTS {tmp} ('
                'id INTEGER NOT NULL PRIMARY KEY, '
                'user_id INTEGER NOT NULL, '
                'organization_id INTEGER NOT NULL, '
                'work_type_id INTEGER, '
                'hours_worked REAL NOT NULL, '
                'description TEXT NOT NULL, '
                'date_created DATETIME NOT NULL, '
                'FOREIGN KEY(user_id) REFERENCES users (id), '
                'FOREIGN KEY(organization_id) REFERENCES organizations (id), '
                'FOREIGN KEY(work_type_id) REFERENCES work_types (id)'
                ')'
            )
        )
        conn.execute(
            text(
                f'INSERT OR IGNORE INTO {tmp} (id, user_id, organization_id, hours_worked, description, date_created) '
                f'SELECT id, user_id, organization_id, hours_worked, description, date_created '
                f'FROM {report_table} WHERE organization_id IS NOT NULL'
            )
        )
        conn.execute(text(f'DROP TABLE {report_table}'))
        conn.execute(text(f'ALTER TABLE {tmp} RENAME TO {report_table}'))


def migrate_reports_work_type_fk():
    """Добавляет колонку work_type_id в таблицу report, если её нет."""
    insp = inspect(db.engine)
    report_table = Report.__tablename__
    if report_table not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns(report_table)}
    if 'work_type_id' not in cols:
        with db.engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE {report_table} ADD COLUMN work_type_id INTEGER REFERENCES work_types(id)'))


def migrate_organizations_inn():
    """Добавляет колонку inn в таблицу organizations, если её нет."""
    insp = inspect(db.engine)
    if 'organizations' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('organizations')}
    if 'inn' not in cols:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE organizations ADD COLUMN inn VARCHAR(12) DEFAULT ''"))


def migrate_report_work_date():
    """Добавляет work_date в таблицу report. Существующим отчётам ставит work_date = date_created."""
    insp = inspect(db.engine)
    if 'report' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('report')}
    if 'work_date' not in cols:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE report ADD COLUMN work_date DATETIME"))
            conn.execute(text("UPDATE report SET work_date = date_created WHERE work_date IS NULL"))


def seed_default_work_types():
    """Создаёт предустановленные типы работ, если таблица пуста."""
    if WorkType.query.first():
        return
    defaults = [
        ('Обычная работа', 'Стандартная рабочая смена'),
        ('Работа в выходные', 'Работа в субботу или воскресенье'),
        ('Сверхурочно', 'Работа сверх нормы'),
        ('Командировка', 'Выездная работа или командировка'),
    ]
    for name, desc in defaults:
        db.session.add(WorkType(name=name, description=desc))
    db.session.commit()
    print("Созданы предустановленные типы работ.")


# ── Инициализация БД ────────────────────────────────────────────────────────────

with app.app_context():
    migrate_reports_organization_fk()
    migrate_reports_work_type_fk()
    migrate_organizations_inn()
    migrate_report_work_date()
    db.create_all()
    seed_default_work_types()
    if not User.query.first():
        admin = User(full_name='Administrator', nickname='admin', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("Создан администратор: admin / admin123")


# ── Маршруты ────────────────────────────────────────────────────────────────────

@app.route('/')
@app.route('/first_page')
def first_page():
    return render_template("first.html")


@app.route('/registration', methods=['GET', 'POST'])
def registration():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        nickname = request.form.get('nickname')
        password = request.form.get('password')
        confirm = request.form.get('confirm')

        if not all([full_name, nickname, password]):
            flash('Заполните все поля', 'danger')
        elif password != confirm:
            flash('Пароли не совпадают', 'danger')
        elif len(password) < 5:
            flash('Пароль должен быть минимум 5 символов', 'danger')
        elif User.query.filter_by(nickname=nickname).first():
            flash('Пользователь с таким ником уже существует', 'danger')
        else:
            new_user = User(full_name=full_name, nickname=nickname)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash('Регистрация успешна! Теперь войдите', 'success')
            return redirect(url_for('login'))

    return render_template("registration.html")


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nickname = request.form.get('nickname')
        password = request.form.get('password')
        user = User.query.filter_by(nickname=nickname).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['nickname'] = user.nickname
            session['role'] = user.role
            session['full_name'] = user.full_name
            flash(f'Добро пожаловать, {user.full_name}!', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin_panel'))
            else:
                return redirect(url_for('workers_panel'))
        else:
            flash('Неверный ник или пароль', 'danger')
    return render_template("login.html")


@app.route('/workers')
def workers_panel():
    if 'user_id' not in session or session.get('role') != 'employee':
        flash('Доступ только для сотрудников', 'warning')
        return redirect(url_for('login'))
    return render_template("workers.html", name=session.get('full_name'))


@app.route('/time_report')
def time_report():
    if 'user_id' not in session or session.get('role') != 'employee':
        flash('Доступ только для сотрудников', 'warning')
        return redirect(url_for('login'))
    return render_template('time_report.html')


@app.route('/my_tasks')
def my_tasks():
    return render_template('my_tasks.html')


@app.route('/my_reports')
def my_reports():
    if 'user_id' not in session or session.get('role') != 'employee':
        flash('Доступ только для сотрудников', 'warning')
        return redirect(url_for('login'))

    reports = (
        Report.query
        .options(joinedload(Report.organization), joinedload(Report.work_type))
        .filter_by(user_id=session['user_id'])
        .order_by(Report.date_created.desc())
        .all()
    )
    return render_template('my_reports.html', reports=reports, delete_form=DeleteReportForm())


@app.route('/my_reports/delete', methods=['POST'])
def delete_my_report():
    if 'user_id' not in session or session.get('role') != 'employee':
        flash('Доступ только для сотрудников', 'warning')
        return redirect(url_for('login'))

    form = DeleteReportForm()
    if form.validate():
        report = db.session.get(Report, int(form.report_id.data))
        if report is None:
            flash('Отчёт не найден', 'danger')
        elif report.user_id != session['user_id']:
            flash('Можно удалять только свои отчёты', 'danger')
        else:
            db.session.delete(report)
            db.session.commit()
            flash('Отчёт удалён', 'success')
    else:
        flash('Не удалось удалить. Обновите страницу и попробуйте снова.', 'danger')
    return redirect(url_for('my_reports'))


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    return render_template('settings.html')


@app.route('/admin')
def admin_panel():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Доступ только для администратора', 'warning')
        return redirect(url_for('login'))
    users = User.query.all()
    return render_template("admin.html", users=users)


@app.route('/admin/staff')
def staff_list():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Доступ запрещён', 'warning')
        return redirect(url_for('login'))
    users = User.query.all()
    return render_template('staff_list.html', users=users)


@app.route('/admin/daily_report')
def daily_report():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Доступ запрещён', 'warning')
        return redirect(url_for('login'))

    date_from = request.args.get('date_from', datetime.now().strftime('%Y-%m-%d'))
    date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))
    work_type_filter = request.args.get('work_type_id', '')

    try:
        from_dt = datetime.strptime(date_from, '%Y-%m-%d')
        to_dt = datetime(
            *datetime.strptime(date_to, '%Y-%m-%d').timetuple()[:3], 23, 59, 59
        )

        query = (
            Report.query
            .options(joinedload(Report.organization), joinedload(Report.work_type))
            .join(User)
            .filter(Report.work_date >= from_dt, Report.work_date <= to_dt)
        )
        if work_type_filter:
            query = query.filter(Report.work_type_id == int(work_type_filter))

        reports = query.order_by(Report.work_date.desc()).all()
        total_hours = sum(r.hours_worked for r in reports)
    except ValueError:
        flash('Некорректный формат даты', 'danger')
        reports = []
        total_hours = 0

    all_work_types = WorkType.query.order_by(WorkType.name).all()
    return render_template(
        'daily_report.html',
        reports=reports,
        total_hours=total_hours,
        date_from=date_from,
        date_to=date_to,
        all_work_types=all_work_types,
        work_type_filter=work_type_filter,
    )


@app.route('/admin/assign_task', methods=['GET', 'POST'])
def assign_task():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Доступ запрещён', 'warning')
        return redirect(url_for('login'))
    if request.method == 'POST':
        flash('Функция в разработке', 'info')
        return redirect(url_for('assign_task'))
    users = User.query.filter_by(role='employee').all()
    return render_template('assign_task.html', users=users)


@app.route('/admin/daily_report/export')
def export_daily_report():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Доступ запрещён', 'warning')
        return redirect(url_for('login'))

    date_from = request.args.get('date_from', datetime.now().strftime('%Y-%m-%d'))
    date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))
    work_type_filter = request.args.get('work_type_id', '')

    try:
        from_dt = datetime.strptime(date_from, '%Y-%m-%d')
        to_dt = datetime(
            *datetime.strptime(date_to, '%Y-%m-%d').timetuple()[:3], 23, 59, 59
        )

        query = (
            Report.query
            .options(joinedload(Report.organization), joinedload(Report.work_type))
            .join(User, Report.user_id == User.id)
            .filter(Report.work_date >= from_dt, Report.work_date <= to_dt)
        )
        if work_type_filter:
            query = query.filter(Report.work_type_id == int(work_type_filter))

        reports = query.order_by(Report.work_date.desc()).all()
    except ValueError:
        flash('Некорректный формат даты', 'danger')
        return redirect(url_for('daily_report'))

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    writer.writerow(['Сотрудник', 'Организация', 'ИНН', 'Тип работы', 'Часов', 'Что выполнено', 'Дата работы', 'Дата создания'])

    for report in reports:
        description = report.description.replace('\n', ' ').replace('\r', ' ').replace(',', ';')

        hours = report.hours_worked
        if isinstance(hours, float) and hours.is_integer():
            hours_str = str(int(hours))
        else:
            hours_str = str(hours).replace('.', ',')

        org_name = report.organization.name if report.organization else ''
        inn = report.organization.inn if report.organization and report.organization.inn else ''
        wt_name = report.work_type.name if report.work_type else ''

        # Дата работы — только дата (ДД.ММ.ГГГГ) в МСК
        msk_work = to_msk(report.work_date) if report.work_date else None
        work_date_str = msk_work.strftime('%d.%m.%Y') if msk_work else ''

        # Дата создания — дата + время в МСК
        msk_created = to_msk(report.date_created)
        created_str = msk_created.strftime('%d.%m.%Y %H:%M') if msk_created else ''

        writer.writerow([report.user.full_name, org_name, inn, wt_name, hours_str, description, work_date_str, created_str])

    csv_content = '\uFEFF' + output.getvalue()
    output.close()

    filename = f"report_{date_from}_to_{date_to}.csv"
    return Response(
        csv_content,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Доступ запрещён', 'warning')
        return redirect(url_for('login'))
    if request.method == 'POST':
        flash('Смена пароля будет реализована позже', 'info')
        return redirect(url_for('admin_settings'))
    return render_template('admin_settings.html')


def _validate_inn(inn):
    """Возвращает (очищенный ИНН, ошибка). Допускает пустую строку."""
    inn = (inn or '').strip()
    if not inn:
        return '', None
    if not inn.isdigit():
        return inn, 'ИНН должен состоять только из цифр'
    if len(inn) not in (10, 12):
        return inn, 'ИНН должен содержать 10 или 12 цифр'
    return inn, None


@app.route('/admin/organizations', methods=['GET', 'POST'])
def admin_organizations():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Доступ запрещён', 'warning')
        return redirect(url_for('login'))

    add_form = AddOrganizationForm()
    delete_form = DeleteOrganizationForm()
    edit_org_id = request.args.get('edit', type=int)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            if add_form.validate_on_submit():
                name = add_form.name.data.strip()
                inn, err = _validate_inn(add_form.inn.data)
                if err:
                    flash(err, 'danger')
                elif Organization.query.filter_by(name=name).first():
                    flash('Организация с таким названием уже существует', 'danger')
                else:
                    db.session.add(Organization(name=name, inn=inn))
                    db.session.commit()
                    flash('Организация добавлена', 'success')
                    return redirect(url_for('admin_organizations'))

        elif action == 'edit':
            org_id = request.form.get('org_id', type=int)
            name = (request.form.get('name') or '').strip()
            inn, err = _validate_inn(request.form.get('inn'))
            if not name:
                flash('Название не может быть пустым', 'danger')
            elif err:
                flash(err, 'danger')
            else:
                org = db.session.get(Organization, org_id)
                if org:
                    existing = Organization.query.filter_by(name=name).first()
                    if existing and existing.id != org.id:
                        flash('Организация с таким названием уже существует', 'danger')
                    else:
                        org.name = name
                        org.inn = inn
                        db.session.commit()
                        flash('Организация обновлена', 'success')
            return redirect(url_for('admin_organizations'))

        elif action == 'delete':
            if delete_form.validate():
                org = db.session.get(Organization, int(delete_form.org_id.data))
                if org is None:
                    flash('Организация не найдена', 'danger')
                else:
                    report_count = Report.query.filter_by(organization_id=org.id).count()
                    # Каскадно удаляем все привязанные отчёты, затем организацию
                    Report.query.filter_by(organization_id=org.id).delete()
                    db.session.delete(org)
                    db.session.commit()
                    if report_count:
                        flash(f'Организация удалена вместе с {report_count} отчётами', 'success')
                    else:
                        flash('Организация удалена', 'success')
            else:
                flash('Не удалось обработать запрос.', 'danger')
            return redirect(url_for('admin_organizations'))

    organizations = Organization.query.order_by(Organization.name).all()
    return render_template(
        'admin_organizations.html',
        organizations=organizations,
        add_form=add_form,
        delete_form=delete_form,
        edit_org_id=edit_org_id,
        edit_form=add_form,
    )


# ── Типы работ (CRUD) ────────────────────────────────────────────────────────────

@app.route('/admin/work_types', methods=['GET', 'POST'])
def admin_work_types():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Доступ запрещён', 'warning')
        return redirect(url_for('login'))

    add_form = AddWorkTypeForm()
    edit_form = EditWorkTypeForm()
    toggle_form = WorkTypeActionForm()
    delete_form = WorkTypeActionForm()

    edit_id = request.args.get('edit', type=int)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            if add_form.validate_on_submit():
                name = add_form.name.data.strip()
                if WorkType.query.filter_by(name=name).first():
                    flash('Тип работы с таким названием уже существует', 'danger')
                else:
                    wt = WorkType(name=name, description=(add_form.description.data or '').strip())
                    db.session.add(wt)
                    db.session.commit()
                    flash('Тип работы добавлен', 'success')
                    return redirect(url_for('admin_work_types'))

        elif action == 'edit':
            wt_id = request.form.get('wt_id', type=int)
            name = (request.form.get('name') or '').strip()
            description = (request.form.get('description') or '').strip()
            if not name:
                flash('Название не может быть пустым', 'danger')
            else:
                wt = db.session.get(WorkType, wt_id)
                if wt:
                    existing = WorkType.query.filter_by(name=name).first()
                    if existing and existing.id != wt.id:
                        flash('Тип работы с таким названием уже существует', 'danger')
                    else:
                        wt.name = name
                        wt.description = description
                        db.session.commit()
                        flash('Тип работы обновлён', 'success')
            return redirect(url_for('admin_work_types'))

        elif action == 'toggle':
            wt_id = request.form.get('wt_id', type=int)
            wt = db.session.get(WorkType, wt_id)
            if wt:
                wt.is_active = not wt.is_active
                db.session.commit()
                flash(f'Тип «{wt.name}» {"активирован" if wt.is_active else "отключён"}', 'success')
            return redirect(url_for('admin_work_types'))

        elif action == 'delete':
            wt_id = request.form.get('wt_id', type=int)
            wt = db.session.get(WorkType, wt_id)
            if wt is None:
                flash('Тип работы не найден', 'danger')
            elif wt.reports:
                flash('Нельзя удалить тип, к которому привязаны отчёты', 'danger')
            else:
                db.session.delete(wt)
                db.session.commit()
                flash('Тип работы удалён', 'success')
            return redirect(url_for('admin_work_types'))

    work_types = WorkType.query.order_by(WorkType.name).all()
    return render_template(
        'admin_work_types.html',
        work_types=work_types,
        add_form=add_form,
        edit_form=edit_form,
        toggle_form=toggle_form,
        delete_form=delete_form,
        edit_id=edit_id,
    )


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('first_page'))


@app.route('/add_report', methods=['GET', 'POST'])
def add_report():
    if 'user_id' not in session:
        flash('Войдите в систему, чтобы добавить отчёт', 'warning')
        return redirect(url_for('login'))

    form = ReportForm()
    organizations = Organization.query.order_by(Organization.name).all()
    work_types = WorkType.query.filter_by(is_active=True).order_by(WorkType.name).all()

    # Заполняем варианты типов работ для SelectField
    form.work_type_id.choices = [(wt.id, wt.name) for wt in work_types]

    today_str = datetime.utcnow().strftime('%Y-%m-%d')

    if form.validate_on_submit():
        name = (form.organization.data or '').strip()
        org = Organization.query.filter_by(name=name).first()
        if not org:
            flash('Выберите организацию из списка подсказок.', 'danger')
        else:
            # Парсим дату работы из формы; если не указана — берём сегодня
            raw_date = request.form.get('work_date', '').strip()
            try:
                work_date = datetime.strptime(raw_date, '%Y-%m-%d') if raw_date else datetime.utcnow()
                # Запрещаем будущие даты
                if work_date.date() > datetime.utcnow().date():
                    work_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            except ValueError:
                work_date = datetime.utcnow()

            report = Report(
                user_id=session['user_id'],
                organization_id=org.id,
                work_type_id=form.work_type_id.data,
                hours_worked=form.hours_worked.data,
                description=form.description.data,
                work_date=work_date,
            )
            db.session.add(report)
            db.session.commit()
            flash('Отчёт успешно добавлен', 'success')
            return redirect(url_for('workers_panel'))

    return render_template('add_report.html', form=form, organizations=organizations, work_types=work_types, today=today_str)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
