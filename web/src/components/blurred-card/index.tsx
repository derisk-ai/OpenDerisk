"use client";
import { EllipsisOutlined } from '@ant-design/icons';
import { Divider, DropDownProps, Dropdown, Tooltip, Typography, Card } from 'antd';
import cls from 'classnames';
import { useTranslation } from 'react-i18next';
import Image from 'next/image';
import React, { useRef, useEffect } from 'react';
import './style.css';

const BlurredCard: React.FC<{
  RightTop?: React.ReactNode;
  Tags?: React.ReactNode;
  LeftBottom?: React.ReactNode;
  RightBottom?: React.ReactNode;
  rightTopHover?: boolean;
  name: string;
  description: string | React.ReactNode;
  logo?: string;
  onClick?: () => void;
  className?: string;
  scene?: string;
  code?: string;
  icon?: string;
}> = ({
  RightTop,
  Tags,
  LeftBottom,
  RightBottom,
  onClick,
  rightTopHover = true,
  logo,
  name,
  description,
  className,
  scene,
  code,
}) => {
  if (typeof description === 'string') {
    description = (
      <p className='line-clamp-2 relative bottom-3 text-ellipsis min-h-[40px] text-sm text-[#5a626d] dark:text-[rgba(255,255,255,0.7)] leading-relaxed mb-3'>
        {description}
      </p>
    );
  }

  return (
    <Card
      className={cls('hover-underline-gradient h-[280px] overflow-hidden transition-all duration-300 group cursor-pointer ring-1 ring-gray-200 dark:ring-gray-700 hover:ring-blue-300 dark:hover:ring-blue-500/50 hover:shadow-lg dark:hover:shadow-gray-900/20', className)}
      onClick={onClick}
      styles={{
        body: {
          padding: '20px',
          background: 'linear-gradient(135deg, rgba(255,255,255,0.3) 0%, rgba(240,244,255,0.2) 100%)',
          borderRadius: '12px',
          backdropFilter: 'blur(10px)',
          backgroundClip: 'padding-box',
          border: '1px solid rgba(255,255,255, 0.4)',
          height: '100%'
        }
      }}
    >
      <div className='h-full flex flex-col justify-between'>
        <div>
          <div className='flex items-start gap-3 mb-4'>
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm p-1.5 ring-1 ring-gray-200 dark:ring-gray-700">
              <img 
                src={logo} 
                alt={name} 
                className='w-10 min-w-10 h-10 object-contain rounded-lg max-w-none' 
                onError={(e) => {
                  const target = e.target as HTMLImageElement;
                  target.onerror = null;
                  target.src = '/icons/colorful-plugin.png';
                }} 
              />
            </div>
            <div className='flex-1 min-w-0'>
              <Tooltip title={name} placement='topLeft'>
                <h3 className='font-bold text-base text-gray-800 dark:text-gray-200 truncate mb-1'>
                  {name}
                </h3>
              </Tooltip>
            </div>
          </div>
          <div className='mb-4'>
            {description}
          </div>
        </div>
        
        <div>
          <div className='mb-3'>{Tags}</div>
          
          <div className='flex justify-between items-center mt-auto'>
            <div className='text-xs text-gray-500 dark:text-gray-400'>{LeftBottom}</div>
            <div>{RightBottom}</div>
          </div>
          
          {code && (
            <>
              <Divider className='my-3' />
              <Typography.Text copyable={true} className='text-xs text-gray-500 dark:text-gray-500'>
                {code}
              </Typography.Text>
            </>
          )}
        </div>
      </div>
    </Card>
  );
};

const ChatButton: React.FC<{
  onClick?: () => void;
  Icon?: React.ReactNode | string;
  text?: string;
  className?: string;
}> = ({ onClick, Icon = '/pictures/card_chat.png', text, className }) => {
  const { t } = useTranslation();
  const displayText = text || t('start_chat');

  if (typeof Icon === 'string') {
    Icon = <Image src={Icon as string} alt={Icon as string} width={17} height={15} />;
  }

  return (
    <button
      className={`flex items-center gap-1.5 text-sm rounded-full bg-gradient-to-r from-blue-500 to-indigo-500 text-white px-4 py-1.5 transition-all duration-200 hover:from-blue-600 hover:to-indigo-600 hover:shadow-md ${className}`}
      onClick={e => {
        e.stopPropagation();
        onClick && onClick();
      }}
    >
      {Icon && <span>{Icon}</span>}
      <span>{displayText}</span>
    </button>
  );
};

const InnerDropdown: React.FC<{ menu: DropDownProps['menu'] }> = ({ menu }) => {
  return (
    <Dropdown
      menu={menu}
      getPopupContainer={node => node.parentNode as HTMLElement}
      placement='bottomRight'
      autoAdjustOverflow={false}
    >
      <EllipsisOutlined className='p-2 hover:bg-white hover:dark:bg-black rounded-md' />
    </Dropdown>
  );
};

export { ChatButton, InnerDropdown };
export default BlurredCard;
