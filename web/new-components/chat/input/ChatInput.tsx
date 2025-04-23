import { ChatContext } from '@/app/chat-context';
import { apiInterceptors, newDialogue } from '@/client/api';
import { STORAGE_INIT_MESSAGE_KET } from '@/utils';
import { Button, Input } from 'antd';
import cls from 'classnames';
import { useRouter } from 'next/router';
import { useContext, useState } from 'react';
import { useTranslation } from 'react-i18next';
interface propsT {
  bodyClassName?: string;
  minRows?: number;
  maxRows?: number;
  sendClassName?: string;
  cneterBtn?: boolean;
}
function ChatInput(prosp: propsT) {
  const {bodyClassName, minRows,maxRows = undefined, sendClassName, cneterBtn = true} = prosp;
  const { setCurrentDialogInfo } = useContext(ChatContext);
  const { t } = useTranslation();
  const router = useRouter();

  const [userInput, setUserInput] = useState<string>('');
  const [isFocus, setIsFocus] = useState<boolean>(false);
  const [isZhInput, setIsZhInput] = useState<boolean>(false);

  const onSubmit = async () => {
    const [, res] = await apiInterceptors(newDialogue({ chat_mode: 'chat_normal' }));
    if (res) {
      setCurrentDialogInfo?.({
        chat_scene: res.chat_mode,
        app_code: res.chat_mode,
      });
      localStorage.setItem(
        'cur_dialog_info',
        JSON.stringify({
          chat_scene: res.chat_mode,
          app_code: res.chat_mode,
        }),
      );
      localStorage.setItem(STORAGE_INIT_MESSAGE_KET, JSON.stringify({ id: res.conv_uid, message: userInput }));
      router.push(`/chat/?scene=chat_normal&id=${res.conv_uid}`);
    }
    setUserInput('');
  };

  return (
    <div
      className={cls(
        `flex flex-1 h-12 p-2 pl-4 ${cneterBtn ? 'items-center' : ''} justify-between bg-white dark:bg-[#242733] dark:border-[#6f7f95] rounded-xl  border-t border-b border-l border-r ${
          isFocus ? 'border-[#0c75fc]' : ''
        }`,
        bodyClassName
      )}
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
        }, sendClassName)}
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
