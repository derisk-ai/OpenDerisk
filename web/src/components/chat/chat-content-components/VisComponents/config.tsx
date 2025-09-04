import ErrorBoundary from '@/components/error-boundary';
import MarkdownCard from './MarkDownCard';
import ThinkCard from './ThinkCard';
import VisContentCard from './VisContentCard';
import VisMsgCard from './VisMsgCard';
import VisPlanCard from './VisPlanCard';
import { VisPlanningWindow } from './VisPlanningWindow';
import VisReportCard from './VisReportCard';
import { VisRunningWindow } from './VisRunningWindow';
import VisRunningWindowMsgCard from './VisRunningWindowMsg';
import VisRunningWindowStepCard from './VisRunningWindowStep';
import VisStepCard from './VisStepCard';
import VisStepListCard from './VisStepListCard';

export const visComponentsRender: { [key: string]: (props: { children: React.ReactNode }) => JSX.Element } = {
  'nex-running-window': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisRunningWindow data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'derisk-running-window': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisRunningWindow data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'nex-planning-window': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisPlanningWindow data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },

  'drsk-content': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisContentCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'derisk-llm-space': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisContentCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'drsk-thinking': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <ThinkCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'nex-report': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisReportCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'nex-msg': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisRunningWindowMsgCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'drsk-plan': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisPlanCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'nex-steps': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisStepListCard propsData={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'nex-step': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisRunningWindowStepCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'drsk-msg': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return <VisMsgCard data={data} />;
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'drsk-step': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisStepCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
};
