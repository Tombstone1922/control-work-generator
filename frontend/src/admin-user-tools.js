const USER_KEY = 'control_work_generator_user';
const TOKEN_KEY = 'control_work_generator_token';
const API_URL = 'http://127.0.0.1:8000';
let historyState = { loading: false, programs: [], generations: [] };

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

function isAssessmentGeneration(item) {
  const total = Number(item?.quality_report?.total_questions || 0);
  const status = String(item?.status || '').toLowerCase();
  const comment = String(item?.review_comment || '').toLowerCase();
  return total === 145 || status.includes('fos') || status.includes('фос') || comment.includes('фос') || comment.includes('оценоч');
}

async function loadHistoryForFallback() {
  if (historyState.loading || historyState.programs.length || historyState.generations.length) return;
  const token = localStorage.getItem(TOKEN_KEY) || '';
  if (!token) return;
  historyState.loading = true;
  try {
    const headers = { Authorization: `Bearer ${token}` };
    const [programsResponse, generationsResponse] = await Promise.all([
      fetch(`${API_URL}/api/programs/`, { headers }),
      fetch(`${API_URL}/api/generation/`, { headers }),
    ]);
    historyState.programs = programsResponse.ok ? await programsResponse.json() : [];
    historyState.generations = generationsResponse.ok ? await generationsResponse.json() : [];
  } catch {
    historyState.programs = [];
    historyState.generations = [];
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

function renderFallbackHistory() {
  const adminPage = document.querySelector('.adminPage');
  if (!adminPage) return;
  const intro = adminPage.querySelector('.adminIntro');
  if (!intro || !intro.textContent.includes('Хранилище')) return;

  const existingReactHistory = adminPage.querySelector('.historyGridThree');
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
  title.textContent = 'История генераций и утверждения';
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

export async function initAdminUserTools() {
  if (!hasUser()) return false;
  document.querySelectorAll('section.notice').forEach((notice) => {
    const title = notice.querySelector('strong')?.textContent || '';
    const buttons = notice.querySelector('.actionGroup');
    if (title.includes('Статус ФОС') && buttons) {
      buttons.style.display = countGeneratedItems() > 0 ? '' : 'none';
    }
  });
  await loadHistoryForFallback();
  renderFallbackHistory();
  return true;
}

initAdminUserTools();
if (typeof window !== 'undefined') {
  window.setInterval(initAdminUserTools, 900);
}
