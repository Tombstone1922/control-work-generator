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
let sentReviewSignature = '';
let approvedFundsSignature = '';

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

function tokenHeaders(json = false) {
  const token = localStorage.getItem(TOKEN_KEY) || '';
  return {
    ...(json ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { ...tokenHeaders(Boolean(options.body)), ...(options.headers || {}) },
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.detail || 'Ошибка запроса.');
  return data;
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

async function loadHistoryForFallback(force = false) {
  const token = localStorage.getItem(TOKEN_KEY) || '';
  if (!token || historyState.loading) return;

  const isFresh = Date.now() - historyState.loadedAt < 5000;
  if (!force && isFresh && (historyState.programs.length || historyState.generations.length || historyState.funds.length)) return;

  historyState.loading = true;
  try {
    const headers = tokenHeaders();
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

function makeHistoryButton(title, detail, onClick) {
  const button = document.createElement('button');
  button.className = 'historyItem';
  button.type = 'button';
  const strong = document.createElement('strong');
  strong.textContent = title;
  const span = document.createElement('span');
  span.textContent = detail;
  button.append(strong, span);
  if (onClick) button.addEventListener('click', onClick);
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
    list.appendChild(makeHistoryButton(mapped.title, mapped.detail, mapped.onClick));
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

function fundTotalItems(fund) {
  return Math.min(
    145,
    Number(fund?.validation?.total_items || fund?.sections?.reduce((sum, section) => sum + Number(section.generated_items || 0), 0) || 145),
  );
}

function fundTitle(fund) {
  return fund?.discipline_name || fund?.title || `ФОС ${String(fund?.fund_id || '').slice(0, 8)}`;
}

async function openReviewFund(fundId) {
  const card = document.querySelector('.sentForReviewBlock') || document.querySelector('.approvedFundsFallback');
  if (!card) return;
  const previous = card.querySelector('.reviewDetailCard');
  previous?.remove();

  const detail = document.createElement('article');
  detail.className = 'notice reviewDetailCard';
  detail.innerHTML = '<strong>Открываем карточку проверки...</strong>';
  card.appendChild(detail);

  try {
    const fund = await requestJson(`/api/assessment-funds/${fundId}`);
    renderReviewDetail(card, fund);
  } catch (error) {
    detail.innerHTML = `<strong>Не удалось открыть ФОС.</strong><p class="muted">${error.message}</p>`;
  }
}

function renderReviewDetail(container, fund) {
  container.querySelector('.reviewDetailCard')?.remove();

  const detail = document.createElement('article');
  detail.className = 'notice reviewDetailCard';

  const title = document.createElement('strong');
  title.textContent = `Карточка проверки: ${fundTitle(fund)}`;
  const meta = document.createElement('p');
  meta.className = 'muted';
  meta.textContent = `${statusLabel(fund.status)} · ${fundTotalItems(fund)} элементов ФОС · ${fund.validation?.completeness_score || 0}% заполненность`;

  const actions = document.createElement('div');
  actions.className = 'actionGroup';

  if (fund.status === 'in_review') {
    const approve = document.createElement('button');
    approve.className = 'primary';
    approve.type = 'button';
    approve.textContent = 'Утвердить ФОС';
    approve.addEventListener('click', () => updateFundReviewStatus(fund.fund_id, 'approved'));

    const revision = document.createElement('button');
    revision.className = 'danger';
    revision.type = 'button';
    revision.textContent = 'Вернуть на доработку';
    revision.addEventListener('click', () => updateFundReviewStatus(fund.fund_id, 'revision_required'));

    actions.append(approve, revision);
  }

  const refresh = document.createElement('button');
  refresh.className = 'secondary';
  refresh.type = 'button';
  refresh.textContent = 'Обновить карточку';
  refresh.addEventListener('click', () => openReviewFund(fund.fund_id));
  actions.appendChild(refresh);

  detail.append(title, meta, actions);
  container.appendChild(detail);
}

async function updateFundReviewStatus(fundId, status) {
  const adminPage = document.querySelector('.adminPage');
  const detail = document.querySelector('.reviewDetailCard');
  try {
    await requestJson(`/api/assessment-funds/${fundId}`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    });
    if (detail) {
      detail.innerHTML = `<strong>${status === 'approved' ? 'ФОС утвержден.' : 'ФОС возвращен на доработку.'}</strong><p class="muted">Списки обновлены.</p>`;
    }
    sentReviewSignature = '';
    approvedFundsSignature = '';
    await loadHistoryForFallback(true);
    renderSentForReviewBlock();
    renderApprovedFundsBlock();
  } catch (error) {
    const errorBox = document.createElement('div');
    errorBox.className = 'alert';
    errorBox.textContent = error.message;
    adminPage?.prepend(errorBox);
  }
}

function renderSentForReviewBlock() {
  const user = currentUser();
  const adminPage = document.querySelector('.adminPage');
  if (!adminPage) return;

  const existing = adminPage.querySelector('.sentForReviewBlock');
  if (!['admin', 'methodist'].includes(user?.role)) {
    existing?.remove();
    sentReviewSignature = '';
    return;
  }

  const intro = adminPage.querySelector('.adminIntro');
  if (!intro || !intro.textContent.includes('Хранилище')) {
    existing?.remove();
    sentReviewSignature = '';
    return;
  }

  const inReviewFunds = historyState.funds.filter((item) => item.status === 'in_review');
  const signature = inReviewFunds.map((item) => `${item.fund_id}:${item.status}:${fundTotalItems(item)}`).join('|');
  if (existing && signature === sentReviewSignature) return;
  sentReviewSignature = signature;
  existing?.remove();

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
  if (!inReviewFunds.length) {
    const empty = document.createElement('p');
    empty.className = 'muted';
    empty.textContent = 'Пока нет материалов, отправленных на проверку.';
    list.appendChild(empty);
  } else {
    inReviewFunds.slice(0, 8).forEach((fund) => {
      list.appendChild(makeHistoryButton(
        fundTitle(fund),
        `${statusLabel(fund.status)} · ${fundTotalItems(fund)} элементов ФОС`,
        () => openReviewFund(fund.fund_id),
      ));
    });
  }
  card.appendChild(list);

  const historyCard = adminPage.querySelector('.historyCard:not(.sentForReviewBlock)');
  if (historyCard) historyCard.insertAdjacentElement('afterend', card);
  else intro.insertAdjacentElement('afterend', card);
}

function renderApprovedFundsBlock() {
  const adminPage = document.querySelector('.adminPage');
  if (!adminPage) return;
  const intro = adminPage.querySelector('.adminIntro');
  if (!intro || !intro.textContent.includes('Хранилище')) return;

  const approvedFunds = historyState.funds.filter((item) => item.status === 'approved');
  const signature = approvedFunds.map((item) => `${item.fund_id}:${item.status}:${fundTotalItems(item)}`).join('|');
  if (signature === approvedFundsSignature && adminPage.querySelector('.approvedFundsFallback')) return;
  approvedFundsSignature = signature;

  let card = adminPage.querySelector('.approvedFundsFallback');
  card?.remove();
  card = document.createElement('section');
  card.className = 'card historyCard approvedFundsFallback';
  const header = document.createElement('div');
  header.className = 'sectionHeader';
  const text = document.createElement('div');
  const title = document.createElement('h2');
  title.textContent = 'Утвержденные ФОС';
  const subtitle = document.createElement('p');
  subtitle.className = 'muted';
  subtitle.textContent = 'Фонды оценочных средств, подтвержденные методистом или администратором.';
  text.append(title, subtitle);
  header.appendChild(text);
  card.appendChild(header);

  const list = document.createElement('div');
  list.className = 'historyItems';
  if (!approvedFunds.length) {
    const empty = document.createElement('p');
    empty.className = 'muted';
    empty.textContent = 'Утвержденные ФОС пока не зафиксированы.';
    list.appendChild(empty);
  } else {
    approvedFunds.slice(0, 8).forEach((fund) => {
      list.appendChild(makeHistoryButton(
        fundTitle(fund),
        `${statusLabel(fund.status)} · ${fundTotalItems(fund)} элементов ФОС`,
        () => openReviewFund(fund.fund_id),
      ));
    });
  }
  card.appendChild(list);

  const revisionBlock = Array.from(adminPage.querySelectorAll('.historyCard')).find((node) => node.textContent.includes('Элементы доработки ФОС'));
  if (revisionBlock) revisionBlock.insertAdjacentElement('beforebegin', card);
  else (adminPage.querySelector('.sentForReviewBlock') || adminPage.querySelector('.historyCard') || intro).insertAdjacentElement('afterend', card);
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
  renderApprovedFundsBlock();
  return true;
}

initAdminUserTools();
if (typeof window !== 'undefined') {
  window.setInterval(initAdminUserTools, 900);
}
