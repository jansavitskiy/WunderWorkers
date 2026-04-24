// admin.js – общие утилиты для админ-панели
document.addEventListener('DOMContentLoaded', () => {
    // Автоматически скрывать flash-сообщения через 4 секунды
    document.querySelectorAll('.alert').forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 4000);
    });

    // Подтверждение удаления (для кнопок с классом confirm-delete)
    document.querySelectorAll('.confirm-delete').forEach(btn => {
        btn.addEventListener('click', (e) => {
            if (!confirm('Вы уверены, что хотите удалить?')) {
                e.preventDefault();
            }
        });
    });

    // Инициализация таблиц с сортировкой (простая, по клику на заголовок)
    document.querySelectorAll('.sortable').forEach(table => {
        const headers = table.querySelectorAll('th');
        headers.forEach((th, index) => {
            th.style.cursor = 'pointer';
            th.addEventListener('click', () => sortTable(table, index));
        });
    });
});

// Функция сортировки таблицы
function sortTable(table, colIndex) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const isNumber = !isNaN(rows[0].children[colIndex].innerText);
    const direction = table.dataset.sortDir === 'asc' ? 'desc' : 'asc';
    rows.sort((a, b) => {
        let aVal = a.children[colIndex].innerText;
        let bVal = b.children[colIndex].innerText;
        if (isNumber) {
            aVal = parseFloat(aVal);
            bVal = parseFloat(bVal);
        }
        if (aVal < bVal) return direction === 'asc' ? -1 : 1;
        if (aVal > bVal) return direction === 'asc' ? 1 : -1;
        return 0;
    });
    rows.forEach(row => tbody.appendChild(row));
    table.dataset.sortDir = direction;
}

// Универсальный toast (если не используется глобальный)
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `alert ${type}`;
    toast.innerText = message;
    toast.style.position = 'fixed';
    toast.style.bottom = '20px';
    toast.style.right = '20px';
    toast.style.zIndex = '9999';
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}