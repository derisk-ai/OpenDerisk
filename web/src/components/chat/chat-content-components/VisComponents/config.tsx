import ErrorBoundary from '@/components/error-boundary';
import VisCode from './VisCode';
import VisCodeIde from './VisCodeIde';
import VisConfirmCard from './VisConfirmCard';
import VisDocCard from './VisDocCard';
import VisDocOutlineCard from './VisDocOutlineCard';
import VisDocReportCard from './VisDocReportCard';
import VisInteracCard from './VisInteracCard';
import VisLLM from './VisLLM';
import VisLsCard from './VisLsCard';
import VisMonitor from './VisMonitor';
import VisReadYuqueCard from './VisReadYuqueCard';
import VisReportCard from './VisReportCard';
import VisUtils from './VisUtils';
import VisKnowledgeSpaceWindow from './VisKnowledgeSpaceWindow';
import VisAgentFolder from './VisAgentFolder';
import { VisRunningWindowV2 } from './VisRunningWindowV2';
import MarkdownCard from './MarkDownCard';
import DThinkCard from './DThinkCard';
import RefsCard from './RefsCard';
import ThinkCard from './ThinkCard';
import VisAgentPlanCard from './VisAgentPlanCard';
import VisContentCard from './VisContentCard';
import VisDAttach from './VisDAttach';
import VisMsgCard from './VisMsgCard';
import VisPlanCard from './VisPlanCard';
import VisPlanningSpaceCard from './VisPlanningSpaceCard';
import { VisPlanningWindow } from './VisPlanningWindow';
import { VisRunningWindow } from './VisRunningWindow';
import VisRunningWindowMsgCard from './VisRunningWindowMsg';
import VisRunningWindowStepCard from './VisRunningWindowStep';
import VisStepCard from './VisStepCard';
import VisStepListCard from './VisStepListCard';
import VisTodoList from './VisTodoList';

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
  'd-thinking': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <DThinkCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'drsk-messages': ({ children }) => {
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
  'drsk-steps': ({ children }) => {
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
  'd-agent-plan': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisAgentPlanCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'd-planning-space': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisPlanningSpaceCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'd-attach': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisDAttach data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'drsk-refs': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <RefsCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'drsk-confirm': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisConfirmCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'drsk-interact': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisInteracCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'vis-code': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisCode {...data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'knowledge-space-window': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisKnowledgeSpaceWindow data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'knowledge-planning-window': ({ children }) => {
    const content = String(children);
    return <MarkdownCard content={content} />;
  },
  'drsk-outline': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisDocOutlineCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'drsk-ls': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisLsCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'drsk-read-yuque': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisReadYuqueCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'drsk-doc': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisDocCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'vis-research-bubble': ({ children }) => {
    const content = String(children);
    return <MarkdownCard content={content} />;
  },
  'drsk-doc-report': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisDocReportCard data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'd-agent-folder': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisAgentFolder data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'd-work': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisRunningWindowV2 data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'd-code': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisCodeIde {...data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'd-monitor': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisMonitor {...data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'd-tool': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisUtils data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'd-llm': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisLLM data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
  'drsk-browser': ({ children }) => {
    const content = String(children);
    return <MarkdownCard content={content} />;
  },
  'd-todo-list': ({ children }) => {
    const content = String(children);
    try {
      const data = JSON.parse(content);
      return (
        <ErrorBoundary fallback={<MarkdownCard content={content} />}>
          <VisTodoList data={data} />
        </ErrorBoundary>
      );
    } catch {
      return <MarkdownCard content={content} />;
    }
  },
};
