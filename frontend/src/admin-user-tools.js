const USER_KEY = 'control_work_generator_user';

export function initAdminUserTools() {
  try {
    JSON.parse(localStorage.getItem(USER_KEY) || 'null');
  } catch {
    return false;
  }
  return true;
}

initAdminUserTools();
