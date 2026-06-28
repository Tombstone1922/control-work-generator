import React from 'react';

function ProjectStatusDashboard({ program, generationsHistory = [] }) {
  const relevantGenerations = program?.program_id
    ? generationsHistory.filter((item) => item.program_id === program.program_id)
    : [];
  const hasControlWork = relevantGenerations.some((item) => !isAssessmentMaterialGeneration(item));
  const hasAssessmentMaterials = relevantGenerations.some(isAssessmentMaterialGeneration);
  const quality = Number(program?.analysis_report?.diagnostics?.quality_score || 0);

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
      title: 'ФОС / ОМ',
      detail: hasAssessmentMaterials ? 'сформирован' : 'ожидает генерацию',
      ready: hasAssessmentMaterials,
    },
    {
      title: 'Банк заданий КР готов',
      detail: hasControlWork ? 'готов к просмотру' : 'ожидает генерацию КР',
      ready: hasControlWork,
    },
    {
      title: 'Банк заданий ОМ готов',
      detail: hasAssessmentMaterials ? 'готов к просмотру' : 'ожидает генерацию ОМ',
      ready: hasAssessmentMaterials,
    },
    {
      title: 'КР готова к экспорту',
      detail: hasControlWork ? 'доступен DOCX' : 'сначала сформируйте КР',
      ready: hasControlWork,
    },
    {
      title: 'ОМ готов к экспорту',
      detail: hasAssessmentMaterials ? 'доступен DOCX' : 'сначала сформируйте ОМ',
      ready: hasAssessmentMaterials,
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
