import ModelIcon from '@/new-components/chat/content/ModelIcon';
import { GPTVis } from '@antv/gpt-vis';
import ReferencesContent from './ReferencesContent';
import markdownComponents, { markdownPlugins, preprocessLaTeX } from './config';

interface Props {
  data: {
    sender: string;
    receiver: string;
    model: string | null;
    markdown: string;
    avatar: string;
    resource: any;
  }[];
}

function AgentMessages({ data }: Props) {
  if (!data || !data.length) return null;
  return (
    <>
      {data.map((item, index) => (
        <div key={index} className='rounded'>
          <div className='flex items-center mb-3 text-sm'>
            {item.model ? (
              <ModelIcon model={item.model} />
            ) : (
              <img src={`/agents/${item.avatar}`} className='flex-0 rounded-2xl w-6 h-6 inline-block' />
            )}
            <div className='ml-2 opacity-70 text-xs'>
              {item.sender}
              <span className='text-blue-500 font-medium pl-1'>@{item.receiver}</span>
            </div>
          </div>
          <div className='whitespace-normal text-xs mb-3'>
            <GPTVis components={markdownComponents} {...markdownPlugins}>
              {preprocessLaTeX(item.markdown)}
            </GPTVis>
          </div>
          {item.resource && item.resource !== 'null' && <ReferencesContent references={item.resource} />}
        </div>
      ))}
    </>
  );
}

export default AgentMessages;
