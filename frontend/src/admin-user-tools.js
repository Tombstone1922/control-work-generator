const USER_KEY = 'control_work_generator_user';

function hasUser() {
  try {
    return Boolean(JSON.parse(localStorage.getItem(USER_KEY) || 'null'));
  } catch {
    return false;
  }
}

function countGeneratedItems() {
  const metrics = document.querySelectorAll('.fosMetricsGrid .metric');
  for (const metric of metrics) {
    const label = metric.querySelector('span')?.textContent?.trim();
    if (label === 'Сформировано заданий') {
      return Number.parseInt(metric.querySelector('strong')?.textContent || '0', 10) || 0;
    }
  }
  return 0;
}

export function initAdminUserTools() {
  if (!hasUser()) return false;
  document.querySelectorAll('section.notice').forEach((notice) => {
    const title = notice.querySelector('strong')?.textContent || '';
    const buttons = notice.querySelector('.actionGroup');
    if (title.includes('Статус ФОС') && buttons) {
      buttons.style.display = countGeneratedItems() > 0 ? '' : 'none';
    }
  });
  return true;
}

initAdminUserTools();
if (typeof window !== 'undefined') {
  window.setInterval(initAdminUserTools, 600);
}
