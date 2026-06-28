const USER_KEY = 'control_work_generator_user';
const TOKEN_KEY = 'control_work_generator_token';
const API_URL = 'http://127.0.0.1:8000';

let historyState = {
  loading: false,
  programs: [],
  generations: [],
  funds: [],
  loadedAt: 0,
};

function currentUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null');
  } catch {
    return null;
  }
}

function hasUser() {
  return Boolean(currentUser());
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

function isAssessmentGeneration(item) {
  const total = Number(item?.quality_report?.total_questions || 0);
  const status = String(item?.status || '').toLowerCase();
  const comment = String(item?.review_comment || '').toLowerCase();
  return total === 145 || status.includes('fos') || status.includes('фос') || comment.includes('фос') || comment.includes('оценоч');
}

async function loadHistoryForFallback() {
  const token = localStorage.getItem(TOKEN_KEY) || '';
  if (!token || historyState.loading) return;

  const isFresh = Date.now() - historyState.loadedAt < 5000;
  if (isFresh && (historyState.programs.length || historyState.generations.length || historyState.funds.length)) return;

  historyState.loading = true;
  try {
    const headers = { Authorization: `Bearer ${token}` };
    const [programsResponse, generationsResponse, fundsResponse] = await Promise.all([
      fetch(`${API_URL}/api/programs/`, { headers }),
      fetch(`${API_URL}/api/generation/`, { headers }),
      fetch(`${API_URL}/api/assessment-funds/`, { headers }),
    ]);
    historyState.programs = programsResponse.ok ? await programsResponse.json() : [];
    historyState.generations = generationsResponse.ok ? await generationsResponse.json() : [];
    historyState.funds = fundsResponse.ok ? await fundsResponse.json() : [];
    historyState.loadedAt = Date.now();
  } catch {
    historyState.programs = [];
    historyState.generations = [];
    historyState.funds = [];
  } finally {
    historyState.loading = false;
  }
}

function makeHistoryButton(title, detail) {
  const button = document.createElement('button');
  button.className = 'historyItem';
  button.type = 'button';
  const strong = document.createElement('strong');
  strong.textContent = title;
  const span = document.createElement('span');
  span.textContent = detail;
  button.append(strong, span);
  return button;
}

function renderColumn(title, items, mapper) {
  const column = document.createElement('div');
  column.className = 'historyColumn';
  const heading = document.createElement('h3');
  heading.textContent = title;
  column.appendChild(heading);
  if (!items.length) {
    const empty = document.createElement('p');
    empty.className = 'muted';
    empty.textContent = 'Пока пусто';
    column.appendChild(empty);
    return column;
  }
  const list = document.createElement('div');
  list.className = 'historyItems';
  items.slice(0, 8).forEach((item) => {
    const mapped = mapper(item);
    list.appendChild(makeHistoryButton(mapped.title, mapped.detail));
  });
  column.appendChild(list);
  return column;
}

function renameHistoryTitles() {
  document.querySelectorAll('h2').forEach((heading) => {
    if (heading.textContent.trim() === 'История генераций и утверждения') {
      heading.textContent = 'Истории генерации';
    }
  });
}

function renderFallbackHistory() {
  const adminPage = document.querySelector('.adminPage');
  if (!adminPage) return;
  const intro = adminPage.querySelector('.adminIntro');
  if (!intro || !intro.textContent.includes('Хранилище')) return;

  const existingReactHistory = adminPage.querySelector('.historyCard:not(.alwaysHistoryFallback) .historyGridThree');
  const existingFallback = adminPage.querySelector('.alwaysHistoryFallback');

  if (existingReactHistory) {
    existingFallback?.remove();
    return;
  }
  if (existingFallback) return;

  const card = document.createElement('section');
  card.className = 'card historyCard alwaysHistoryFallback';
  const header = document.createElement('div');
  header.className = 'sectionHeader';
  const headerText = document.createElement('div');
  const title = document.createElement('h2');
  title.textContent = 'Истории генерации';
  const subtitle = document.createElement('p');
  subtitle.className = 'muted';
  subtitle.textContent = 'Ранее загруженные РПД, сформированные оценочные материалы и контрольные работы.';
  headerText.append(title, subtitle);
  header.appendChild(headerText);

  const grid = document.createElement('div');
  grid.className = 'historyGrid historyGridThree';
  const assessment = historyState.generations.filter(isAssessmentGeneration);
  const controls = historyState.generations.filter((item) => !isAssessmentGeneration(item));
  grid.append(
    renderColumn('РПД', historyState.programs, (item) => ({
      title: item.filename,
      detail: `${item.topics?.length || 0} тем · качество анализа РПД ${item.analysis_report?.diagnostics?.quality_score || 0}%`,
    })),
    renderColumn('Генерации оценочных материалов', assessment, (item) => ({
      title: `${String(item.session_id || '').slice(0, 8)}...`,
      detail: `Сформировано · ${item.quality_report?.total_questions || 0} элементов ФОС`,
    })),
    renderColumn('Генерации контрольных работ', controls, (item) => ({
      title: `${String(item.session_id || '').slice(0, 8)}...`,
      detail: `Сформировано · ${item.quality_report?.total_questions || 0} заданий`,
    })),
  );
  card.append(header, grid);
  intro.insertAdjacentElement('afterend', card);
}

function statusLabel(status) {
  return ({
    draft: 'Черновик',
    generated: 'Сформировано',
    in_review: 'На проверке',
    revision_required: 'Требует доработки',
    approved: 'Утверждено',
  }[status] || status || 'статус не указан');
}

function renderSentForReviewBlock() {
  const user = currentUser();
  const adminPage = document.querySelector('.adminPage');
  if (!adminPage) return;

  const existing = adminPage.querySelector('.sentForReviewBlock');
  if (!['admin', 'methodist'].includes(user?.role)) {
    existing?.remove();
    return;
  }

  const intro = adminPage.querySelector('.adminIntro');
  if (!intro || !intro.textContent.includes('Хранилище')) {
    existing?.remove();
    return;
  }

  existing?.remove();
  const inReviewFunds = historyState.funds.filter((item) => item.status === 'in_review');
  const inReviewGenerations = historyState.generations.filter((item) => item.status === 'in_review');
  const items = inReviewFunds.length ? inReviewFunds : inReviewGenerations;

  const card = document.createElement('section');
  card.className = 'card historyCard sentForReviewBlock';
  const header = document.createElement('div');
  header.className = 'sectionHeader';
  const text = document.createElement('div');
  const title = document.createElement('h2');
  title.textContent = 'Отправленные на проверку';
  const subtitle = document.createElement('p');
  subtitle.className = 'muted';
  subtitle.textContent = 'ФОС и оценочные материалы, ожидающие проверки методистом или администратором.';
  text.append(title, subtitle);
  header.appendChild(text);
  card.appendChild(header);

  const list = document.createElement('div');
  list.className = 'historyItems';
  if (!items.length) {
    const empty = document.createElement('p');
    empty.className = 'muted';
    empty.textContent = 'Пока нет материалов, отправленных на проверку.';
    list.appendChild(empty);
  } else {
    items.slice(0, 8).forEach((item) => {
      const titleText = item.discipline_name || item.title || item.filename || `${String(item.session_id || item.fund_id || '').slice(0, 8)}...`;
      const total = item.quality_report?.total_questions || item.validation?.total_items || item.total_questions || 145;
      list.appendChild(makeHistoryButton(titleText, `${statusLabel(item.status)} · ${total} элементов ФОС`));
    });
  }
  card.appendChild(list);

  const historyCard = adminPage.querySelector('.historyCard:not(.sentForReviewBlock)');
  if (historyCard) historyCard.insertAdjacentElement('afterend', card);
  else intro.insertAdjacentElement('afterend', card);
}

function hideMethodistDashboards() {
  const user = currentUser();
  const shouldHide = user?.role === 'methodist';
  document.querySelectorAll('.projectStatusDashboard, .adminDashboard').forEach((node) => {
    node.style.display = shouldHide ? 'none' : '';
  });
}

export async function initAdminUserTools() {
  if (!hasUser()) return false;

  document.querySelectorAll('section.notice').forEach((notice) => {
    const title = notice.querySelector('strong')?.textContent || '';
    const buttons = notice.querySelector('.actionGroup');
    if (title.includes('Статус ФОС') && buttons) {
      buttons.style.display = countGeneratedItems() > 0 ? '' : 'none';
    }
  });

  hideMethodistDashboards();
  renameHistoryTitles();
  await loadHistoryForFallback();
  renderFallbackHistory();
  renderSentForReviewBlock();
  return true;
}

initAdminUserTools();
if (typeof window !== 'undefined') {
  window.setInterval(initAdminUserTools, 900);
}
