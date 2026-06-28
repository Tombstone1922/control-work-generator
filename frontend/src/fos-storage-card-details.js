const USER_KEY = 'control_work_generator_user';
const TOKEN_KEY = 'control_work_generator_token';
const API_URL = 'http://127.0.0.1:8000';

let cachedFunds = [];
let lastLoadAt = 0;
let isLoading = false;

function hasUser() {
  try {
    return Boolean(JSON.parse(localStorage.getItem(USER_KEY) || 'null'));
  } catch {
    return false;
  }
}

function headers() {
  const token = localStorage.getItem(TOKEN_KEY) || '';
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function loadFunds(force = false) {
  if (!hasUser() || isLoading) return;
  if (!force && Date.now() - lastLoadAt < 3000 && cachedFunds.length) return;
  isLoading = true;
  try {
    const response = await fetch(`${API_URL}/api/assessment-funds/`, { headers: headers() });
    cachedFunds = response.ok ? await response.json() : [];
    lastLoadAt = Date.now();
  } catch {
    cachedFunds = [];
  } finally {
    isLoading = false;
  }
}

function normalize(value) {
  return String(value || '').trim().toLowerCase();
}

function formatDate(value) {
  if (!value) return 'время не указано';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function countItems(fund) {
  const sectionCount = (fund.sections || []).reduce((sum, section) => sum + Number(section.generated_items || 0), 0);
  return Math.min(145, Number(fund.validation?.total_items || sectionCount || 145));
}

function cardTitle(fund) {
  return fund.discipline_name || fund.title || '';
}

function detailText(fund, statusText) {
  const rpd = fund.program_filename || fund.program?.filename || 'РПД не указана';
  const time = formatDate(fund.created_at || fund.updated_at);
  return `РПД: ${rpd} · Сформировано: ${time} · ${statusText} · ${countItems(fund)} элементов ФОС`;
}

function findSection(title) {
  return Array.from(document.querySelectorAll('.historyCard')).find((section) => (
    Array.from(section.querySelectorAll('h2')).some((heading) => heading.textContent.trim() === title)
  ));
}

function enrichSection(title, status, statusText) {
  const section = findSection(title);
  if (!section) return;
  const cards = Array.from(section.querySelectorAll('.historyItem'));
  const funds = cachedFunds.filter((fund) => fund.status === status);
  const used = new Set();

  cards.forEach((card) => {
    const strong = card.querySelector('strong');
    const span = card.querySelector('span');
    if (!strong || !span) return;

    const titleKey = normalize(strong.textContent);
    const index = funds.findIndex((fund, fundIndex) => !used.has(fundIndex) && normalize(cardTitle(fund)) === titleKey);
    const fallbackIndex = funds.findIndex((fund, fundIndex) => !used.has(fundIndex));
    const pickedIndex = index >= 0 ? index : fallbackIndex;
    if (pickedIndex < 0) return;

    used.add(pickedIndex);
    span.textContent = detailText(funds[pickedIndex], statusText);
  });
}

function enrichStorageCards() {
  if (!cachedFunds.length) return;
  enrichSection('Отправленные на проверку', 'in_review', 'На проверке');
  enrichSection('Элементы доработки ФОС', 'revision_required', 'Требует доработки');
  enrichSection('Утвержденные ФОС', 'approved', 'Утверждено');
}

async function runFosStorageCardDetails() {
  await loadFunds();
  enrichStorageCards();
}

if (typeof window !== 'undefined') {
  window.addEventListener('load', runFosStorageCardDetails);
  window.setInterval(runFosStorageCardDetails, 1200);
}
