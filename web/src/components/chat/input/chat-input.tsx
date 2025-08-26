import { ChatContext } from '@/contexts';
import { apiInterceptors, initConfig, newDialogue } from '@/client/api';
import { STORAGE_INIT_MESSAGE_KET } from '@/utils';
import { Button, Input } from 'antd';
import cls from 'classnames';
import { useRouter } from 'next/navigation';
import { useContext, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface propsT {
  bodyClassName?: string;
  minRows?: number;
  maxRows?: number;
  sendClassName?: string;
  cneterBtn?: boolean;
  isGoPath?: boolean;
  input?: string;
}

function ChatInput(prosp: propsT) {
  const {
    bodyClassName,
    minRows = 1,
    maxRows = undefined,
    sendClassName,
    cneterBtn = true,
    isGoPath = false,
    input = '',
  } = prosp;

  const { setCurrentDialogInfo } = useContext(ChatContext);
  const { t } = useTranslation();
  const router = useRouter();

  const [userInput, setUserInput] = useState<string>('');
  const [isFocus, setIsFocus] = useState<boolean>(false);
  const [isZhInput, setIsZhInput] = useState<boolean>(false);

  const onSubmit = async () => {
    const [, res] = await apiInterceptors(newDialogue({ app_code: 'chat_normal' }));
    if (res) {
      localStorage.setItem(STORAGE_INIT_MESSAGE_KET, JSON.stringify({ id: res.conv_uid, message: userInput }));
      router.push(`/chat/?app_code=chat_normal&conv_uid=${res.conv_uid}`);
    }
    setUserInput('');
  };

  return (
    <div
      className={cls(`flex flex-1 h-12 p-2 pl-4 items-center justify-between bg-white dark:bg-[#242733] dark:border-[#6f7f95] rounded-xl border border-gray-300 ${
        isFocus ? 'border-[#0c75fc]' : ''
      }`, bodyClassName)}
    >
      <Input.TextArea
        placeholder={t('input_tips')}
        className='w-full resize-none border-0 p-0 focus:shadow-none'
        value={userInput}
        autoSize={{ minRows, maxRows }}
        onKeyDown={e => {
          if (e.key === 'Enter') {
            if (e.shiftKey) {
              return;
            }
            if (isZhInput) {
              return;
            }
            e.preventDefault();
            if (!userInput.trim()) {
              return;
            }
            onSubmit();
          }
        }}
        onChange={e => {
          setUserInput(e.target.value);
        }}
        onFocus={() => {
          setIsFocus(true);
        }}
        onBlur={() => setIsFocus(false)}
        onCompositionStart={() => setIsZhInput(true)}
        onCompositionEnd={() => setIsZhInput(false)}
      />
      <Button
        type='primary'
        className={cls('flex items-center justify-center w-14 h-8 rounded-lg text-sm  bg-button-gradient border-0', {
          'opacity-40 cursor-not-allowed': !userInput.trim(),
        })}
        onClick={() => {
          if (!userInput.trim()) {
            return;
          }
          onSubmit();
        }}
      >
        {t('sent')}
      </Button>
    </div>
  );
}

export default ChatInput;
