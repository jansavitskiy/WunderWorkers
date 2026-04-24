from flask import Flask, render_template, request, redirect, url_for, session, flash
from models.db import db, bcrypt
from models import User   
from datetime import datetime


app = Flask(__name__)
app.secret_key = 'секретный-ключ-смени-его'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workers.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


db.init_app(app)
bcrypt.init_app(app)


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
    return render_template('my_reports.html')


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
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('daily_report.html', today=today)


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


@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Доступ запрещён', 'warning')
        return redirect(url_for('login'))
    if request.method == 'POST':
        flash('Смена пароля будет реализована позже', 'info')
        return redirect(url_for('admin_settings'))
    return render_template('admin_settings.html')


# Выход
@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('first_page'))


# Создание таблиц (один раз, можно вынести в отдельную команду)
with app.app_context():
    db.create_all()
    # Создаём администратора по умолчанию, если нет ни одного пользователя
    if not User.query.first():
        admin = User(full_name='Administrator', nickname='admin', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("Создан администратор: admin / admin123")



if __name__ == '__main__':
    app.run(debug=True)
