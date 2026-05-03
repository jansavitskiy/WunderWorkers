from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from models.db import db, bcrypt
from models import User, Organization
from datetime import datetime
import csv
import io
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, TextAreaField, SubmitField, HiddenField
from wtforms.validators import DataRequired, NumberRange
from sqlalchemy import inspect, text
from sqlalchemy.orm import joinedload

app = Flask(__name__)
app.secret_key = 'секретный-ключ-смени-его'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workers.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_ENABLED'] = True


db.init_app(app)
bcrypt.init_app(app)


# Новая модель отчёта сотрудника.
# Каждая запись привязана к пользователю и хранит факт выполненной работы.
class Report(db.Model):
    __tablename__ = 'report'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    hours_worked = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref=db.backref('reports', lazy=True))
    organization = db.relationship('Organization', back_populates='reports')


class ReportForm(FlaskForm):
    # Название должно совпадать с одной из организаций в datalist (проверка в маршруте).
    organization = StringField('Название организации', validators=[DataRequired()])
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
    submit = SubmitField('Добавить организацию')


class DeleteOrganizationForm(FlaskForm):
    """Без SubmitField: в шаблоне используется обычная <button>, иначе validate_on_submit не проходит."""
    org_id = HiddenField(validators=[DataRequired()])


class DeleteReportForm(FlaskForm):
    report_id = HiddenField(validators=[DataRequired()])


def migrate_reports_organization_fk():
    """Добавляет organization_id и переносит данные из старого текстового поля organization."""
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

    # Старый столбец organization (TEXT NOT NULL) остаётся в SQLite после ALTER; без пересборки
    # таблицы INSERT в новую схему падает с NOT NULL constraint failed: report.organization
    insp = inspect(db.engine)
    cols = {c['name'] for c in insp.get_columns(report_table)}
    if 'organization' not in cols:
        return

    tmp = '_report_migrate_tmp'
    with db.engine.begin() as conn:
        conn.execute(
            text(
                f'CREATE TABLE {tmp} ('
                'id INTEGER NOT NULL PRIMARY KEY, '
                'user_id INTEGER NOT NULL, '
                'organization_id INTEGER NOT NULL, '
                'hours_worked REAL NOT NULL, '
                'description TEXT NOT NULL, '
                'date_created DATETIME NOT NULL, '
                'FOREIGN KEY(user_id) REFERENCES users (id), '
                'FOREIGN KEY(organization_id) REFERENCES organizations (id)'
                ')'
            )
        )
        conn.execute(
            text(
                f'INSERT INTO {tmp} (id, user_id, organization_id, hours_worked, description, date_created) '
                f'SELECT id, user_id, organization_id, hours_worked, description, date_created '
                f'FROM {report_table} WHERE organization_id IS NOT NULL'
            )
        )
        conn.execute(text(f'DROP TABLE {report_table}'))
        conn.execute(text(f'ALTER TABLE {tmp} RENAME TO {report_table}'))


# Главная страница
@app.route('/')
@app.route('/first_page')
def first_page():
    return render_template("first.html")


# Регистрация
@app.route('/registration', methods=['GET', 'POST'])
def registration():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        nickname = request.form.get('nickname')
        password = request.form.get('password')
        confirm = request.form.get('confirm')

        # Валидация
        if not all([full_name, nickname, password]):
            flash('Заполните все поля', 'danger')
        elif password != confirm:
            flash('Пароли не совпадают', 'danger')
        elif len(password) < 5:
            flash('Пароль должен быть минимум 5 символов', 'danger')
        elif User.query.filter_by(nickname=nickname).first():
            flash('Пользователь с таким ником уже существует', 'danger')
        else:
            # Создаём нового пользователя
            new_user = User(full_name=full_name, nickname=nickname)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash('Регистрация успешна! Теперь войдите', 'success')
            return redirect(url_for('login'))

    return render_template("registration.html")


# Вход
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


# Панель сотрудника
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
    # аналогично
    return render_template('my_tasks.html')


@app.route('/my_reports')
def my_reports():
    # Показываем только отчёты текущего сотрудника.
    if 'user_id' not in session or session.get('role') != 'employee':
        flash('Доступ только для сотрудников', 'warning')
        return redirect(url_for('login'))

    reports = (
        Report.query.options(joinedload(Report.organization))
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


# Панель администратора
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
    selected_date = request.args.get('date') or datetime.now().strftime('%Y-%m-%d')
    reports = []
    total_hours = 0.0

    try:
        date_from = datetime.strptime(selected_date, '%Y-%m-%d')
        date_to = datetime(date_from.year, date_from.month, date_from.day, 23, 59, 59, 999999)
        reports = (
            Report.query.options(joinedload(Report.organization))
            .join(User, Report.user_id == User.id)
            .filter(Report.date_created >= date_from, Report.date_created <= date_to)
            .order_by(Report.date_created.desc())
            .all()
        )
        total_hours = sum(report.hours_worked for report in reports)
    except ValueError:
        flash('Некорректный формат даты', 'danger')
        selected_date = datetime.now().strftime('%Y-%m-%d')

    return render_template(
        'daily_report.html',
        today=selected_date,
        reports=reports,
        total_hours=total_hours
    )


@app.route('/admin/assign_task', methods=['GET', 'POST'])
def assign_task():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Доступ запрещён', 'warning')
        return redirect(url_for('login'))
    if request.method == 'POST':
        flash('Функция в разработке', 'info')
        return redirect(url_for('assign_task'))
    users = User.query.filter_by(role='employee').all()  # только сотрудников
    return render_template('assign_task.html', users=users)


@app.route('/admin/daily_report/export')
def export_daily_report():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Доступ запрещён', 'warning')
        return redirect(url_for('login'))

    selected_date = request.args.get('date') or datetime.now().strftime('%Y-%m-%d')
    try:
        date_from = datetime.strptime(selected_date, '%Y-%m-%d')
    except ValueError:
        flash('Некорректный формат даты', 'danger')
        return redirect(url_for('daily_report'))

    date_to = datetime(date_from.year, date_from.month, date_from.day, 23, 59, 59, 999999)
    reports = (
        Report.query.options(joinedload(Report.organization))
        .join(User, Report.user_id == User.id)
        .filter(Report.date_created >= date_from, Report.date_created <= date_to)
        .order_by(Report.date_created.desc())
        .all()
    )

    # Используем список списков для данных
    data = []
    headers = ['Сотрудник', 'Организация', 'Часов', 'Что выполнено', 'Время отправки']
    data.append(headers)
    
    for report in reports:
        # Очищаем описание от лишних переносов строк и запятых
        description = report.description.replace('\n', ' ').replace('\r', ' ').replace(',', ';')
        row = [
            report.user.full_name,
            report.organization.name,
            report.hours_worked,
            description,
            report.date_created.strftime('%d.%m.%Y %H:%M')
        ]
        data.append(row)

    # Создаём CSV с правильной кодировкой UTF-8 с BOM
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL, delimiter=';')  # разделитель ; для Excel
    
    for row in data:
        writer.writerow(row)
    
    csv_content = output.getvalue()
    output.close()
    
    # Добавляем BOM для корректного отображения кириллицы в Excel
    csv_content_with_bom = '\uFEFF' + csv_content
    
    filename = f"daily_reports_{selected_date}.csv"

    return Response(
        csv_content_with_bom,
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


@app.route('/admin/organizations', methods=['GET', 'POST'])
def admin_organizations():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Доступ запрещён', 'warning')
        return redirect(url_for('login'))

    add_form = AddOrganizationForm()
    delete_form = DeleteOrganizationForm()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            add_form = AddOrganizationForm()
            if add_form.validate_on_submit():
                name = add_form.name.data.strip()
                if Organization.query.filter_by(name=name).first():
                    flash('Организация с таким названием уже существует', 'danger')
                else:
                    db.session.add(Organization(name=name))
                    db.session.commit()
                    flash('Организация добавлена', 'success')
                    return redirect(url_for('admin_organizations'))
        elif action == 'delete':
            delete_form = DeleteOrganizationForm()
            if delete_form.validate():
                org = db.session.get(Organization, int(delete_form.org_id.data))
                if org is None:
                    flash('Организация не найдена', 'danger')
                elif Report.query.filter_by(organization_id=org.id).first():
                    flash('Нельзя удалить организацию, пока к ней привязаны отчёты', 'danger')
                else:
                    db.session.delete(org)
                    db.session.commit()
                    flash('Организация удалена', 'success')
            else:
                flash('Не удалось обработать запрос. Проверьте, что страница не устарела, и попробуйте снова.', 'danger')
            return redirect(url_for('admin_organizations'))

    organizations = Organization.query.order_by(Organization.name).all()
    return render_template(
        'admin_organizations.html',
        organizations=organizations,
        add_form=add_form,
        delete_form=delete_form,
    )


# Выход
@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('first_page'))


# Создание таблиц и перенос схемы отчётов на связь с организациями
with app.app_context():
    migrate_reports_organization_fk()
    # Создаём администратора по умолчанию, если нет ни одного пользователя
    if not User.query.first():
        admin = User(full_name='Administrator', nickname='admin', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("Создан администратор: admin / admin123")


@app.route('/add_report', methods=['GET', 'POST'])
def add_report():
    # Добавлять отчёты могут только авторизованные пользователи.
    if 'user_id' not in session:
        flash('Войдите в систему, чтобы добавить отчёт', 'warning')
        return redirect(url_for('login'))

    form = ReportForm()
    organizations = Organization.query.order_by(Organization.name).all()

    if form.validate_on_submit():
        name = (form.organization.data or '').strip()
        org = Organization.query.filter_by(name=name).first()
        if not org:
            flash('Выберите организацию из списка подсказок (сначала добавьте её в настройках администратора).', 'danger')
        else:
            report = Report(
                user_id=session['user_id'],
                organization_id=org.id,
                hours_worked=form.hours_worked.data,
                description=form.description.data,
            )
            db.session.add(report)
            db.session.commit()
            flash('Отчёт успешно добавлен', 'success')
            return redirect(url_for('workers_panel'))

    return render_template('add_report.html', form=form, organizations=organizations)

if __name__ == '__main__':
    app.run(debug=True)
