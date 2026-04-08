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
import VisDAttachList from './VisDAttachList';
import VisMsgCard from './VisMsgCard';
import VisPlanCard from './VisPlanCard';
import VisPlanningSpaceCard from './VisPlanningSpaceCard';
import { VisPlanningWindow } from './VisPlanningWindow';
import { VisRunningWindow } from './VisRunningWindow';
import VisRunningWindowMsgCard from './VisRunningWindowMsg';
import VisRunningWindowStepCard from './VisRunningWindowStep';
import VisStepCard from './VisStepCard';
import VisStepListCard from './VisStepListCard';
import { parseFirstJson } from '@/utils/json';
import VisTodoList from './VisTodoList';
import VisParseError from './VisParseError';
import VisStatusNotification from './VisStatusNotification';
import VisAuthorizationCard from './VisAuthorizationCard';
import VisConfirmResponse from './VisConfirmResponse';
import VisSystemEvents from './VisSystemEvents';
import VisManusLeftPanel from './VisManusLeftPanel';
import VisManusRightPanel from './VisManusRightPanel';
import VisSqlQuery from './VisSqlQuery';
import { ee, EVENTS } from '@/utils/event-emitter';
import {
  OutputRenderer,
  TerminalRenderer,
  CodeExecutionRenderer,
  HtmlTabbedRenderer,
  SkillScriptRenderer,
  SkillCardRenderer,
} from './VisManusRightPanel/renderers';

export const visComponentsRender: { [key: string]: (props: { children: React.ReactNode }) => JSX.Element } = {
  'nex-running-window': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="nex-running-window" />}>
          <VisRunningWindow data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="nex-running-window" />;
    }
  },
  'derisk-running-window': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="derisk-running-window" />}>
          <VisRunningWindow data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="derisk-running-window" />;
    }
  },
  'nex-planning-window': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="nex-planning-window" />}>
          <VisPlanningWindow data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="nex-planning-window" />;
    }
  },

  'drsk-content': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="drsk-content" />}>
          <VisContentCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-content" />;
    }
  },
  'derisk-llm-space': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="derisk-llm-space" />}>
          <VisContentCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="derisk-llm-space" />;
    }
  },
  'drsk-thinking': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="drsk-thinking" />}>
          <ThinkCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-thinking" />;
    }
  },
  'nex-report': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="nex-report" />}>
          <VisReportCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="nex-report" />;
    }
  },
  'nex-msg': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="nex-msg" />}>
          <VisRunningWindowMsgCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="nex-msg" />;
    }
  },
  'drsk-plan': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="drsk-plan" />}>
          <VisPlanCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-plan" />;
    }
  },
  'nex-steps': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="nex-steps" />}>
          <VisStepListCard propsData={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="nex-steps" />;
    }
  },
  'nex-step': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="nex-step" />}>
          <VisRunningWindowStepCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="nex-step" />;
    }
  },
  'drsk-msg': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return <VisMsgCard data={data} />;
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-msg" />;
    }
  },
  'drsk-step': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="drsk-step" />}>
          <VisStepCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-step" />;
    }
  },
  'd-thinking': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-thinking" />}>
          <DThinkCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-thinking" />;
    }
  },
  'drsk-messages': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="drsk-messages" />}>
          <VisContentCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-messages" />;
    }
  },
  'drsk-steps': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="drsk-steps" />}>
          <VisStepListCard propsData={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-steps" />;
    }
  },
  'd-agent-plan': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-agent-plan" />}>
          <VisAgentPlanCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-agent-plan" />;
    }
  },
  'd-planning-space': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-planning-space" />}>
          <VisPlanningSpaceCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-planning-space" />;
    }
  },
  'd-attach': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-attach" />}>
          <VisDAttach data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-attach" />;
    }
  },
  'd-attach-list': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-attach-list" />}>
          <VisDAttachList data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-attach-list" />;
    }
  },
  'drsk-refs': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="drsk-refs" />}>
          <RefsCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-refs" />;
    }
  },
  'drsk-confirm': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="drsk-confirm" />}>
          <VisConfirmCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-confirm" />;
    }
  },
  'drsk-interact': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="drsk-interact" />}>
          <VisInteracCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-interact" />;
    }
  },
  'vis-code': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="vis-code" />}>
          <VisCode {...data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="vis-code" />;
    }
  },
  'knowledge-space-window': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="knowledge-space-window" />}>
          <VisKnowledgeSpaceWindow data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="knowledge-space-window" />;
    }
  },
  'knowledge-planning-window': ({ children }) => {
    const content = String(children);
    return <MarkdownCard content={content} />;
  },
  'drsk-outline': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="drsk-outline" />}>
          <VisDocOutlineCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-outline" />;
    }
  },
  'drsk-ls': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="drsk-ls" />}>
          <VisLsCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-ls" />;
    }
  },
  'drsk-read-yuque': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="drsk-read-yuque" />}>
          <VisReadYuqueCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-read-yuque" />;
    }
  },
  'drsk-doc': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="drsk-doc" />}>
          <VisDocCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-doc" />;
    }
  },
  'vis-research-bubble': ({ children }) => {
    const content = String(children);
    return <MarkdownCard content={content} />;
  },
  'drsk-doc-report': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="drsk-doc-report" />}>
          <VisDocReportCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-doc-report" />;
    }
  },
  'd-agent-folder': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-agent-folder" />}>
          <VisAgentFolder data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-agent-folder" />;
    }
  },
  'd-work': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-work" />}>
          <VisRunningWindowV2 data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-work" />;
    }
  },
  'd-code': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-code" />}>
          <VisCodeIde {...data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-code" />;
    }
  },
  'd-monitor': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-monitor" />}>
          <VisMonitor {...data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-monitor" />;
    }
  },
  'd-tool': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-tool" />}>
          <VisUtils data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-tool" />;
    }
  },
  'd-llm': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-llm" />}>
          <VisLLM data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-llm" />;
    }
  },
  'drsk-browser': ({ children }) => {
    const content = String(children);
    return <MarkdownCard content={content} />;
  },
  'd-todo-list': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-todo-list" />}>
          <VisTodoList data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-todo-list" />;
    }
  },
  'd-status-notification': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-status-notification" />}>
          <VisStatusNotification {...data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-status-notification" />;
    }
  },
  'drsk-confirm-response': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="drsk-confirm-response" />}>
          <VisConfirmResponse data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="drsk-confirm-response" />;
    }
  },
  'd-authorization': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-authorization" />}>
          <VisAuthorizationCard data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-authorization" />;
    }
  },
  'd-system-events': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-system-events" />}>
          <VisSystemEvents data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-system-events" />;
    }
  },
  // Manus 双面板布局组件
  'manus-left-panel': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="manus-left-panel" />}>
          <VisManusLeftPanel
            data={data}
            onStepClick={(stepId) => {
              ee.emit(EVENTS.CLICK_FOLDER, { uid: stepId });
              ee.emit(EVENTS.OPEN_PANEL);
            }}
          />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="manus-left-panel" />;
    }
  },
  'manus-right-panel': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="manus-right-panel" />}>
          <VisManusRightPanel data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="manus-right-panel" />;
    }
  },
  'manus-output': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="manus-output" />}>
          <OutputRenderer outputs={Array.isArray(data.outputs) ? data.outputs : [data]} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="manus-output" />;
    }
  },
  'manus-terminal': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="manus-terminal" />}>
          <TerminalRenderer command={data.command} outputs={data.outputs || []} status={data.status || 'completed'} title={data.title} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="manus-terminal" />;
    }
  },
  'manus-code-exec': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="manus-code-exec" />}>
          <CodeExecutionRenderer outputs={data.outputs || []} language={data.language} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="manus-code-exec" />;
    }
  },
  'manus-html-preview': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="manus-html-preview" />}>
          <HtmlTabbedRenderer outputs={data.outputs || []} title={data.title} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="manus-html-preview" />;
    }
  },
  'manus-skill-script': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="manus-skill-script" />}>
          <SkillScriptRenderer outputs={data.outputs || []} skillName={data.skillName} scriptName={data.scriptName} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="manus-skill-script" />;
    }
  },
  'manus-skill-card': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="manus-skill-card" />}>
          <SkillCardRenderer outputs={data.outputs || []} skillName={data.skillName} skillDescription={data.skillDescription} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="manus-skill-card" />;
    }
  },
  'd-sql-query': ({ children }) => {
    const content = String(children);
    try {
      const data = parseFirstJson(content);
      return (
        <ErrorBoundary fallbackRender={({ error }) => <VisParseError content={content} error={error} componentName="d-sql-query" />}>
          <VisSqlQuery data={data} />
        </ErrorBoundary>
      );
    } catch (e) {
      return <VisParseError content={content} error={e} componentName="d-sql-query" />;
    }
  },
};
