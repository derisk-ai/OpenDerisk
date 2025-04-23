import ChatInput from '@/new-components/chat/input/ChatInput';
import { Layout } from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';

const { Header, Footer, Sider, Content } = Layout;
const headerStyle: React.CSSProperties = {
  textAlign: 'center',
  // backgroundColor: ,
};
const contentStyle: React.CSSProperties = {
  textAlign: 'center',
  height: 'auto',
};
const HomePang = () => {
  const { t, i18n } = useTranslation();

  return (
    <div className='h-screen flex flex-col'>
      
       <div className='flex-1 flex flex-col justify-center items-center '>
        <div>
          <img className='w-100 h-60' src='/logo_zh_latest.png' alt='logo' />
        </div>
        <div className='text-4xl '>
          <span className='mr-2'>🚀</span>
          <span className='text-transparent bg-clip-text font-bold bg-gradient-to-r from-sky-500 to-indigo-800'>
            {t('homeTitle')}
          </span>
        </div>
        <div className='flex flex-col mt-6' style={{width: '900px'}}>
          <ChatInput bodyClassName='h-32 items-end' minRows={9} maxRows={9} cneterBtn={false}/>
          <div className='text-xl px-5 mt-6 font-serif font-thin text-center'>{t('homeTip')}</div>
        </div>
       
      </div>
      
    </div>
  );
};

export default HomePang;
