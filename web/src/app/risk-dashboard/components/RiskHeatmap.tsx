'use client';

import React, { useState, useMemo } from 'react';
import { Card, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { HeatmapDataPoint, riskLevelMap } from '../mock/data';

interface RiskHeatmapProps {
  data: HeatmapDataPoint[];
  loading?: boolean;
}

// Generate all days for a year (grouped by weeks)
function generateYearWeeks(year: number): Date[][] {
  const weeks: Date[][] = [];
  const startDate = new Date(year, 0, 1);
  const endDate = new Date(year, 11, 31);

  const firstSunday = new Date(startDate);
  firstSunday.setDate(firstSunday.getDate() - firstSunday.getDay());

  let currentWeekStart = new Date(firstSunday);
  while (currentWeekStart <= endDate || currentWeekStart.getMonth() === 0) {
    const week: Date[] = [];
    for (let i = 0; i < 7; i++) {
      const day = new Date(currentWeekStart);
      day.setDate(day.getDate() + i);
      week.push(day);
    }
    weeks.push(week);
    currentWeekStart.setDate(currentWeekStart.getDate() + 7);
    if (currentWeekStart.getFullYear() > year) break;
  }

  return weeks;
}

// Get month info for label positioning
function getMonthColumns(weeks: Date[][], year: number): { label: string; startCol: number; span: number }[] {
  const months: { label: string; startCol: number; span: number }[] = [];
  const monthNames = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

  let lastMonth = -1;
  let monthStartCol = 0;

  weeks.forEach((week, colIndex) => {
    const yearDay = week.find(d => d.getFullYear() === year);
    if (!yearDay) return;

    const month = yearDay.getMonth();

    if (month !== lastMonth) {
      if (lastMonth !== -1) {
        months.push({
          label: monthNames[lastMonth],
          startCol: monthStartCol,
          span: colIndex - monthStartCol
        });
      }
      lastMonth = month;
      monthStartCol = colIndex;
    }
  });

  if (lastMonth !== -1) {
    months.push({
      label: monthNames[lastMonth],
      startCol: monthStartCol,
      span: weeks.length - monthStartCol
    });
  }

  return months;
}

export default function RiskHeatmap({ data, loading }: RiskHeatmapProps) {
  const { t } = useTranslation();

  const currentYear = new Date().getFullYear();
  const availableYears = [currentYear, currentYear - 1, currentYear - 2];
  const [selectedYear, setSelectedYear] = useState(currentYear);

  const dataMap = useMemo(() => {
    const map = new Map<string, HeatmapDataPoint>();
    data.forEach((point) => {
      map.set(point.date, point);
    });
    return map;
  }, [data]);

  const weeks = useMemo(() => generateYearWeeks(selectedYear), [selectedYear]);
  const monthColumns = useMemo(() => getMonthColumns(weeks, selectedYear), [weeks, selectedYear]);

  const dayLabels = ['', '一', '', '三', '', '五', ''];

  const getMostSevereLevel = (point: HeatmapDataPoint | undefined): string => {
    if (!point) return 'empty';
    if (point.redCount > 0) return 'red';
    if (point.yellowCount > 0) return 'yellow';
    if (point.blueCount > 0) return 'blue';
    if (point.greenCount > 0) return 'green';
    return 'empty';
  };

  const getCellColor = (date: Date): string => {
    const dateStr = date.toISOString().split('T')[0];
    const point = dataMap.get(dateStr);
    const level = getMostSevereLevel(point);
    if (level === 'empty') return '#ebedf0';
    return riskLevelMap[level].color;
  };

  const getTooltipContent = (date: Date): string => {
    const dateStr = date.toISOString().split('T')[0];
    const point = dataMap.get(dateStr);
    if (!point) {
      return `${dateStr}\n${t('risk_no_data') || '无数据'}`;
    }
    return `${dateStr}\n${t('risk_level_green')}: ${point.greenCount}\n${t('risk_level_blue')}: ${point.blueCount}\n${t('risk_level_yellow')}: ${point.yellowCount}\n${t('risk_level_red')}: ${point.redCount}`;
  };

  const isInSelectedYear = (date: Date): boolean => {
    return date.getFullYear() === selectedYear;
  };

  return (
    <Card
      title={<span>{t('risk_heatmap_title')}</span>}
      loading={loading}
      className="mb-6"
      styles={{ body: { padding: '12px' } }}
    >
      {/* Container: flex layout to separate heatmap and year selector */}
      <div style={{ display: 'flex', gap: '8px' }}>
        {/* Heatmap area - takes all remaining space */}
        <div style={{ flex: '1 1 auto', minWidth: 0 }}>
          {/* Month labels - using CSS Grid with flexible columns */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: `20px repeat(${weeks.length}, minmax(0, 1fr))`,
              marginBottom: '4px',
              columnGap: '4px',
              height: '18px',
            }}
          >
            <div />
            {monthColumns.map((month, idx) => (
              <div
                key={idx}
                className="text-xs text-gray-500"
                style={{
                  gridColumn: `${month.startCol + 2} / span ${month.span}`,
                }}
              >
                {month.label}
              </div>
            ))}
          </div>

          {/* Day labels and Heatmap grid - using CSS Grid with flexible columns */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: `20px repeat(${weeks.length}, minmax(0, 1fr))`,
              gridTemplateRows: 'repeat(7, minmax(0, 1fr))',
              columnGap: '4px',
              rowGap: '2px',
              height: '95px', // 固定高度
            }}
          >
            {/* Day labels */}
            {dayLabels.map((day, index) => (
              <div
                key={index}
                className="text-xs text-gray-400 text-right"
                style={{
                  gridColumn: 1,
                  gridRow: index + 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'flex-end',
                  paddingRight: '2px',
                }}
              >
                {day}
              </div>
            ))}

            {/* Heatmap cells - each cell fills its grid cell */}
            {weeks.map((week, weekIndex) =>
              week.map((date, dayIndex) => (
                <Tooltip key={`${weekIndex}-${dayIndex}`} title={getTooltipContent(date)}>
                  <div
                    className="rounded-sm cursor-pointer hover:ring-1 hover:ring-gray-400"
                    style={{
                      gridColumn: weekIndex + 2,
                      gridRow: dayIndex + 1,
                      width: '100%',
                      height: '100%',
                      backgroundColor: getCellColor(date),
                      opacity: isInSelectedYear(date) ? 1 : 0.3,
                    }}
                  />
                </Tooltip>
              ))
            )}
          </div>

          {/* Legend */}
          <div className="flex items-center justify-end gap-3 mt-3 text-xs">
            <span className="text-gray-400">{t('risk_legend')}:</span>
            {Object.entries(riskLevelMap).map(([key, value]) => (
              <div key={key} className="flex items-center gap-1">
                <div
                  className="w-2.5 h-2.5 rounded-sm"
                  style={{ backgroundColor: value.color }}
                />
                <span className="text-gray-500">{value.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Year selector - fixed width on the right */}
        <div style={{ flex: '0 0 auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div className="text-sm text-gray-500 mb-1">{t('risk_select_year') || '年份'}</div>
          {availableYears.map((year) => (
            <button
              key={year}
              onClick={() => setSelectedYear(year)}
              className={`px-3 py-1 text-sm rounded transition-colors ${
                selectedYear === year
                  ? 'bg-blue-500 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {year}
            </button>
          ))}
        </div>
      </div>
    </Card>
  );
}