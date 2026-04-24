// Переключение тёмной/светлой темы
function initTheme() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        document.body.classList.add('dark');
    }

    const btn = document.createElement('button');
    btn.className = 'theme-switch';
    btn.innerHTML = document.body.classList.contains('dark') ? '☀️ Светлая' : '🌙 Тёмная';

    
    btn.style.padding = '8px 12px';
    btn.style.borderRadius = '4px';
    btn.style.cursor = 'pointer';
    btn.style.fontSize = '14px';
    btn.style.fontFamily = 'inherit';
    btn.style.border = '1px solid #ccc';
    btn.style.transition = 'all 0.2s ease';

    
    function updateButtonStyle() {
        const isDark = document.body.classList.contains('dark');
        if (isDark) {
            btn.style.backgroundColor = '#333';
            btn.style.color = '#fff';
            btn.style.borderColor = '#555';
        } else {
            btn.style.backgroundColor = '#f9f9f9';
            btn.style.color = '#000';
            btn.style.borderColor = '#ccc';
        }
    }

    updateButtonStyle();

    btn.onclick = () => {
        document.body.classList.toggle('dark');
        const isDark = document.body.classList.contains('dark');
        localStorage.setItem('theme', isDark ? 'dark' : 'light');
        btn.innerHTML = isDark ? '☀️ Светлая' : '🌙 Тёмная';
        updateButtonStyle();
    };

    document.body.appendChild(btn);
}

// Валидация формы регистрации на клиенте
function validateRegistrationForm() {
    const form = document.querySelector('form');
    if (!form) return;
    const password = form.querySelector('input[name="password"]');
    const confirm = form.querySelector('input[name="confirm"]');
    if (password && confirm) {
        confirm.addEventListener('input', () => {
            if (password.value !== confirm.value) {
                confirm.setCustomValidity('Пароли не совпадают');
            } else {
                confirm.setCustomValidity('');
            }
        });
        password.addEventListener('input', () => {
            if (password.value.length < 5) {
                password.setCustomValidity('Минимум 5 символов');
            } else {
                password.setCustomValidity('');
            }
        });
    }
}

// Плавное появление уведомлений (можно добавить к flash)
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `alert ${type}`;
    toast.innerText = message;
    const container = document.querySelector('.container');
    container.insertBefore(toast, container.firstChild);
    setTimeout(() => toast.remove(), 3000);
}

// Запуск после загрузки DOM
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    validateRegistrationForm();
    
    // Автоматически скрыть flash-сообщения через 4 секунды
    document.querySelectorAll('.alert').forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 4000);
    });
});
