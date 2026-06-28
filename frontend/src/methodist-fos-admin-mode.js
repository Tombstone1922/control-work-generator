const USER_KEY = 'control_work_generator_user';

function storedUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null');
  } catch {
    return null;
  }
}

function findAppFiber() {
  const rootNode = document.querySelector('.appShell');
  if (!rootNode) return null;
  const key = Object.keys(rootNode).find((item) => item.startsWith('__reactFiber$'));
  let fiber = key ? rootNode[key] : null;
  while (fiber) {
    if (fiber.type?.name === 'App') return fiber;
    fiber = fiber.return;
  }
  return null;
}

function dispatchAppHook(index, value) {
  const appFiber = findAppFiber();
  if (!appFiber?.memoizedState) return false;
  let hook = appFiber.memoizedState;
  for (let i = 0; i < index; i += 1) hook = hook?.next;
  if (!hook?.queue?.dispatch) return false;
  hook.queue.dispatch(value);
  return true;
}

function enableMethodistFosAdminMode() {
  const user = storedUser();
  if (user?.role !== 'methodist') return;
  const isFosScreen = Boolean(document.querySelector('.fosPage, .fosCard, .itemBank'));
  if (!isFosScreen) return;

  dispatchAppHook(5, false);

  document.querySelectorAll('.success').forEach((node) => {
    if (node.textContent.includes('ФОС открыт из хранилища')) node.style.display = 'none';
  });

  document.querySelectorAll('.notice').forEach((node) => {
    if (
      node.textContent.includes('Режим методиста')
      || node.textContent.includes('Режим просмотра')
      || node.textContent.includes('недоступны для редактирования')
    ) {
      node.style.display = 'none';
    }
  });
}

if (typeof window !== 'undefined') {
  window.addEventListener('load', enableMethodistFosAdminMode);
  window.setInterval(enableMethodistFosAdminMode, 500);
}
