import React from 'react';

function ProjectStatusDashboard({ program, generationsHistory = [], activePage }) {
  const relevantGenerations = program?.program_id
    ? generationsHistory.filter((item) => item.program_id === program.program_id)
    : [];
  const hasControlWork = relevantGenerations.some((item) => !isAssessmentMaterialGeneration(item));
  const hasFosGeneration = relevantGenerations.some(isAssessmentMaterialGeneration);
  const quality = Number(program?.analysis_report?.diagnostics?.quality_score || 0);
  const isOnFos = activePage === 'fos';

  const steps = [
    {
      title: 'РПД загружена',
      detail: program ? program.filename : 'ожидает файл',
      ready: Boolean(program),
    },
    {
      title: 'Анализ выполнен',
      detail: program ? `${quality}% качество анализа` : 'нет анализа',
      ready: Boolean(program && quality > 0),
    },
    {
      title: 'Контрольная',
      detail: hasControlWork ? 'сформирована' : 'не сформирована',
      ready: hasControlWork,
    },
    {
      title: 'ФОС',
      detail: hasFosGeneration || isOnFos ? 'модуль готов' : 'ожидает генерацию',
      ready: hasFosGeneration || isOnFos,
    },
    {
      title: 'Банк заданий',
      detail: hasFosGeneration ? 'готов к просмотру' : 'можно сформировать',
      ready: hasFosGeneration,
    },
    {
      title: 'Экспорт',
      detail: hasControlWork || hasFosGeneration ? 'доступен DOCX' : 'будет доступен после генерации',
      ready: hasControlWork || hasFosGeneration,
    },
  ];

  return (
    <section className="projectStatusDashboard card" aria-label="Статус проекта">
      <div className="projectStatusHeader">
        <div>
          <p className="eyebrow">Состояние проекта</p>
          <h2>Конвейер подготовки материалов</h2>
        </div>
        <span className="projectStatusScore">{steps.filter((step) => step.ready).length}/{steps.length}</span>
      </div>
      <div className="projectStatusGrid">
        {steps.map((step) => (
          <article className={step.ready ? 'projectStatusItem projectStatusItemReady' : 'projectStatusItem'} key={step.title}>
            <span className="projectStatusIcon">{step.ready ? '✓' : '•'}</span>
            <div>
              <strong>{step.title}</strong>
              <small>{step.detail}</small>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function isAssessmentMaterialGeneration(item) {
  const total = Number(item?.quality_report?.total_questions || 0);
  const status = String(item?.status || '').toLowerCase();
  const comment = String(item?.review_comment || '').toLowerCase();
  return total === 145 || status.includes('fos') || status.includes('фос') || comment.includes('фос') || comment.includes('оценоч');
}

export default ProjectStatusDashboard;
