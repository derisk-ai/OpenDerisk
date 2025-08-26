import { ChartId } from '@antv/ava';
import { CustomChartsType } from '../charts';

export type BackEndChartType =
  | 'response_line_chart'
  | 'response_bar_chart'
  | 'response_pie_chart'
  | 'response_scatter_chart'
  | 'response_area_chart'
  | 'response_heatmap_chart'
  | 'response_table';

type ChartType = ChartId | CustomChartsType;

export const getChartType = (backendChartType: BackEndChartType): ChartType[] => {
  if (backendChartType === 'response_line_chart') {
    return ['multi_line_chart', 'multi_measure_line_chart'];
  }
  if (backendChartType === 'response_bar_chart') {
    return ['multi_measure_column_chart'];
  }
  if (backendChartType === 'response_pie_chart') {
    return ['pie_chart'];
  }
  if (backendChartType === 'response_scatter_chart') {
    return ['scatter_plot'];
  }
  if (backendChartType === 'response_area_chart') {
    return ['area_chart'];
  }
  if (backendChartType === 'response_heatmap_chart') {
    return ['heatmap'];
  }
  return [];
};

import { ChartRef as G2Chart } from '@berryv/g2-react';

const getChartCanvas = (chart: G2Chart) => {
  if (!chart) return;
  const chartContainer = chart.getContainer();
  const canvasNode = chartContainer.getElementsByTagName('canvas')[0];
  return canvasNode;
};

/** 获得 g2 Chart 实例的 dataURL */
function toDataURL(chart: G2Chart) {
  const canvasDom = getChartCanvas(chart);
  if (canvasDom) {
    const dataURL = canvasDom.toDataURL('image/png');
    return dataURL;
  }
}

/**
 * 图表图片导出
 * @param chart chart 实例
 * @param name 图片名称
 */
export function downloadImage(chart: G2Chart, name: string = 'Chart') {
  const link = document.createElement('a');
  const filename = `${name}.png`;

  setTimeout(() => {
    const dataURL = toDataURL(chart);
    if (dataURL) {
      link.addEventListener('click', () => {
        link.download = filename;
        link.href = dataURL;
      });
      const e = document.createEvent('MouseEvents');
      e.initEvent('click', false, false);
      link.dispatchEvent(e);
    }
  }, 16);
}

