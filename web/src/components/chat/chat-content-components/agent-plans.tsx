import { CheckOutlined, ClockCircleOutlined } from '@ant-design/icons';

interface Props {
  data: {
    name: string;
    num: number;
    status: 'complete' | 'todo';
    agent: string;
    markdown: string;
  }[];
}
/**
 * AgentPlans component that displays a list of plans.
 * It contains no GPT-Vis components.
 */
function AgentPlans({ data }: Props) {
  if (!data || !data.length) return null;

  return (
    <div className='flex flex-col'>
      {data.map((item, index) => {
        return (
          <div key={index} className='mb-4'>
            <div className='flex-row mb-1'>
              <span className='text-sm'>{item.agent}</span>
              {item.status === 'complete' ? (
                <CheckOutlined className='!text-green-500 ml-2' />
              ) : (
                <ClockCircleOutlined className='!text-gray-500 ml-2' />
              )}
            </div>
            <div className='text-xs break-all text-gray-500'>{item.name}</div>
          </div>
        );
      })}
    </div>
  );
}

export default AgentPlans;
