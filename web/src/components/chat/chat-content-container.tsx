import {
  VerticalAlignBottomOutlined,
  VerticalAlignTopOutlined,
} from "@ant-design/icons";
import React, {
  forwardRef,
  memo,
  useContext,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import BasicChatContent from "./content/basic-chat-content";
import TaskChatContent from "./content/task-chat-content";
import { ChatContentContext } from '@/contexts';

// eslint-disable-next-line no-empty-pattern
const ChatContentContainer = (props: { ctrl: AbortController; }, ref: React.ForwardedRef<any>) => {
  const { ctrl } = props;
  const { appInfo } = useContext(ChatContentContext);
  const containerRef = useRef<HTMLDivElement>(null);
  const [showScrollButtons, setShowScrollButtons] = useState<boolean>(false);
  const [isAtTop, setIsAtTop] = useState<boolean>(true);
  const [isAtBottom, setIsAtBottom] = useState<boolean>(false);

  useImperativeHandle(ref, () => {
    return containerRef.current;
  });

  // 布局
  const isDoubleVis = useMemo(()=>{
    return  appInfo?.layout?.chat_layout?.reuse_name === 'derisk_vis_window'|| appInfo?.layout?.chat_layout?.name === 'derisk_vis_window' || false;
  },[appInfo?.layout?.chat_layout?.name, appInfo?.layout?.chat_layout?.reuse_name]);

  return (
    <div ref={containerRef} className="flex flex-1 h-full w-full overflow-hidden">
      {isDoubleVis ? <TaskChatContent ctrl={ctrl} /> : <BasicChatContent ctrl={ctrl} />}
    </div>
  );
};

export default memo(forwardRef(ChatContentContainer));
