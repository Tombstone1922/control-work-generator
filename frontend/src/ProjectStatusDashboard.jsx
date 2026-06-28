import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';

const API_URL = 'http://127.0.0.1:8000';
const TOKEN_KEY = 'control_work_generator_token';
const FOS_TOTAL_ITEMS = 145;

function ProjectStatusDashboard({ api, program, generationsHistory = [] }) {
  const [assessmentStatus, setAssessmentStatus] = useState({ items: 0, funds: 0, isLoading: false });
  const effectiveApi = useMemo(() => {
    if (api) return api;
    const token = localStorage.getItem(TOKEN_KEY) || '';
    return axios.create({
      baseURL: API_URL,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  }, [api]);

  const relevantGenerations = program?.program_id
    ? generationsHistory.filter((item) => item.program_id === program.program_id)
    : [];
  const hasControlWork = relevantGenerations.some((item) => !isAssessmentMaterialGeneration(item));
  const hasAssessmentGeneration = relevantGenerations.some(isAssessmentMaterialGeneration);
  const hasAssessmentItems = assessmentStatus.items > 0;
  const hasAssessmentMaterials = hasAssessmentGeneration || hasAssessmentItems;
  const displayedAssessmentItems = Math.min(Number(assessmentStatus.items || FOS_TOTAL_ITEMS), FOS_TOTAL_ITEMS);
  const quality = Number(program?.analysis_report?.diagnostics?.quality_score || 0);

  useEffect(() => {
    if (!effectiveApi || !program?.program_id) {
      setAssessmentStatus({ items: 0, funds: 0, isLoading: false });
      return undefined;
    }

    let cancelled = false;

    async function loadAssessmentStatus() {
      try {
        setAssessmentStatus((current) => ({ ...current, isLoading: true }));
        const fundsResponse = await effectiveApi.get('/api/assessment-funds/');
        const relatedFunds = fundsResponse.data.filter((fund) => fund.program_id === program.program_id);
        let generatedItems = relatedFunds.reduce((sum, fund) => (
          sum + (fund.sections || []).reduce((sectionSum, section) => sectionSum + Number(section.generated_items || 0), 0)
        ), 0);

        if (generatedItems === 0 && relatedFunds.length > 0) {
          const itemResponses = await Promise.allSettled(
            relatedFunds.map((fund) => effectiveApi.get(`/api/assessment-items/${fund.fund_id}`)),
          );
          generatedItems = itemResponses.reduce((sum, result) => (
            result.status === 'fulfilled' ? sum + Number(result.value.data?.length || 0) : sum
          ), 0);
        }

        if (!cancelled) {
          setAssessmentStatus({ items: generatedItems, funds: relatedFunds.length, isLoading: false });
        }
      } catch {
        if (!cancelled) setAssessmentStatus({ items: 0, funds: 0, isLoading: false });
      }
    }

    loadAssessmentStatus();
    const intervalId = window.setInterval(loadAssessmentStatus, 3000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [effectiveApi, program?.program_id]);

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
      detail: hasAssessmentMaterials ? `${displayedAssessmentItems} заданий сформировано` : 'ожидает генерацию',
      ready: hasAssessmentMaterials,
    },
    {
      title: 'Банк заданий КР готов',
      detail: hasControlWork ? 'готов к просмотру' : 'ожидает генерацию КР',
      ready: hasControlWork,
    },
    {
      title: 'Банк заданий ОМ готов',
      detail: hasAssessmentMaterials ? `${displayedAssessmentItems} заданий в банке` : 'ожидает задания в банк',
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
  return total === FOS_TOTAL_ITEMS || status.includes('fos') || status.includes('фос') || comment.includes('фос') || comment.includes('оценоч');
}

export default ProjectStatusDashboard;
