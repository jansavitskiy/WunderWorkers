// workers.js — лёгкий скрипт для панели сотрудника
document.addEventListener('DOMContentLoaded', () => {

    const buttons = document.querySelectorAll('.feature-btn');

    buttons.forEach(btn => {
        btn.addEventListener('click', (e) => {

            const url = btn.getAttribute('data-url');
            if (url) {

                window.location.href = url;
            } else {

                showToast('Функция в разработке', 'info');
                e.preventDefault();
            }
        });
    });
});

// Функция для красивого уведомления (toast)
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `alert ${type}`;
    toast.textContent = message;
    toast.style.position = 'fixed';
    toast.style.bottom = '20px';
    toast.style.right = '20px';
    toast.style.maxWidth = '300px';
    toast.style.zIndex = '9999';
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
