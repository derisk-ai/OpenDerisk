import { getSuggestions } from '@/client/api';
import ChatInput from '@/new-components/chat/input/ChatInput';
import { List } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

const HomePang = () => {
  const [suggestions, setSuggestions] = useState([]);
  const [input, setInput] = useState('');
  const { t } = useTranslation();

  useEffect(() => {
    getSuggestions().then(({ data }) => {
      setSuggestions(data.data);
    });
  }, []);

  function onSuggestionClick(item: any) {
    return () => {
      setInput(item);
    };
  }

  return (
    <div className='h-screen flex flex-col items-center justify-center'>
      <div className='flex-1 flex flex-col justify-center items-center w-4/5'>
        <div className='text-4xl w-full justify-center flex items-center font-bold text-slate-800 dark:text-slate-200'>
          <span className='mr-2'>🚀</span>
          <span className='text-transparent bg-clip-text font-bold bg-gradient-to-r from-sky-500 to-indigo-800'>
            {t('homeTitle')}
          </span>
        </div>
        <div className='flex flex-col mt-6 w-full' style={{ width: '900px' }}>
          <ChatInput
            input={input}
            isGoPath={true}
            bodyClassName='h-24 items-end'
            minRows={2}
            maxRows={8}
            cneterBtn={false}
          />
        </div>
        <div className='flex flex-row w-full items-center justify-center mt-4 mb-4'>
          <List
            className='mt-6 w-4/5 max-h-[400px] overflow-y-auto'
            size='small'
            itemLayout='horizontal'
            dataSource={suggestions}
            renderItem={(item, idx) => (
              <List.Item
                className='cursor-pointer group/item hover:bg-slate-200'
                onClick={onSuggestionClick(item)}
              >{`${idx + 1}. ${item}`}</List.Item>
            )}
          />
        </div>
        <div className='text-xl px-5 mt-6 font-serif font-thin text-center'>{t('homeTip')}</div>
      </div>
    </div>
  );
};

export default HomePang;
