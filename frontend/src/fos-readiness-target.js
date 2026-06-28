const FOS_TOTAL_ITEMS = 145;

function normalizeFosReadinessTarget() {
  const pills = document.querySelectorAll('.readinessPill');

  pills.forEach((pill) => {
    const label = pill.querySelector('small')?.textContent?.trim();
    const value = pill.querySelector('strong');

    if (label !== 'Задания' || !value) return;

    const [rawCurrent] = value.textContent.split('/');
    const current = Number.parseInt(rawCurrent, 10);
    const safeCurrent = Number.isFinite(current) ? Math.min(current, FOS_TOTAL_ITEMS) : 0;

    value.textContent = `${safeCurrent}/${FOS_TOTAL_ITEMS}`;
  });
}

if (typeof window !== 'undefined') {
  window.addEventListener('load', normalizeFosReadinessTarget);

  const observer = new MutationObserver(normalizeFosReadinessTarget);
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
  });
}
