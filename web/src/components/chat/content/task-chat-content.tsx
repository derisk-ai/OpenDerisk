import ChatContent from "./chat-content";
import { ChatContentContext } from "@/contexts";
import { IChatDialogueMessageSchema } from "@/types/chat";
import { cloneDeep } from "lodash";
import React, {
  memo,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import ChatInputPanel from "@/components/chat/input/chat-input-panel";
import { v4 as uuid } from "uuid";
import { useDetailPanel } from "./chat-detail-content";
import ChatDetailContent from "./chat-detail-content";
import ChatHeader from "../header/chat-header";

interface TaskChatContentProps {
  ctrl: AbortController;
}

const TaskChatContent: React.FC<TaskChatContentProps> = ({ ctrl }) => {
  const scrollableRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const {
    history,
    isShowDetail,
    isDebug
  } = useContext(ChatContentContext);

  const { runningWindowMarkdown } = useDetailPanel(history);
  const [jsonModalOpen, setJsonModalOpen] = useState(false);
  const [jsonValue, setJsonValue] = useState<string>("");

  const showMessages = useMemo(() => {
    const tempMessage: IChatDialogueMessageSchema[] = cloneDeep(history);
    return tempMessage
      .filter((item) => ["view", "human"].includes(item.role))
      .map((item) => {
        return {
          ...item,
          key: uuid(),
        };
      });
  }, [history]);

  useEffect(() => {
    setTimeout(() => {
      scrollableRef.current?.scrollTo(0, scrollableRef.current?.scrollHeight);
    }, 50);
  }, [history, history[history.length - 1]?.context]);

  return (
    <div className="flex flex-1 h-full w-full
    ">
      <div className={`${isDebug ? 'bg-[transparent]' : 'bg-white'}  dark:bg-[rgba(255,255,255,0.16)] flex flex-1 p-2 justify-center flex-1 w-full`}>
        {/* planning */}
        <div className="flex flex-col w-2/5 pr-2 border-gray-300 flex-1">
          <div className="h-full flex-1 overflow-y-scroll" ref={scrollRef}>
            <ChatHeader isScrollToTop={true} />
            {!!showMessages.length &&
              showMessages.map((content, index) => {
                return (
                  <ChatContent
                    key={index}
                    content={content}
                    onLinkClick={() => {
                      setJsonModalOpen(true);
                      setJsonValue(JSON.stringify(content?.context, null, 2));
                    }}
                    messages={showMessages}
                  />
                );
              })}
          </div>
          <div className="w-full flex justify-center">
            {/* @ts-ignore */}
            <ChatInputPanel ctrl={ctrl} />
          </div>
        </div>
        {/* running */}
        {isShowDetail && <div className="flex flex-col w-3/5 pl-2 border-dashed border-l border-[#F1F5F9] h-full" id="running-window">
           <ChatDetailContent content={runningWindowMarkdown} />
        </div>}
      </div>
    </div>
  );
};

export default memo(TaskChatContent);
