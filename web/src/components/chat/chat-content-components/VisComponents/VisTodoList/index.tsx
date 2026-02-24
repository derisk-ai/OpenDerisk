import React, { useMemo, useState } from 'react';
import { VisTodoListWrap } from './style';
import { UnorderedListOutlined, UpOutlined, DownOutlined } from '@ant-design/icons';

interface TodoItemData {
  id: string;
  title: string;
  status: 'pending' | 'working' | 'completed' | 'failed';
  index: number;
}

interface ITodoListData {
  uid?: string;
  type?: string;
  mission?: string;
  items?: TodoItemData[];
  current_index?: number;
}

interface IProps {
  otherComponents?: any;
  data: ITodoListData;
}

const VisTodoList: React.FC<IProps> = ({ data }) => {
  const items: TodoItemData[] = data.items || [];
  const [expanded, setExpanded] = useState(true);

  const toggleExpand = () => {
    setExpanded(!expanded);
  };

  const progress = useMemo(() => {
    if (items.length === 0) return { completed: 0, total: 0 };
    const completed = items.filter((item) => item.status === 'completed').length;
    return { completed, total: items.length };
  }, [items]);

  const isCompleted = (status: string) => status === 'completed';

  return (
    <VisTodoListWrap>
      <div className="todolist-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        <div className="header-left">
          <UnorderedListOutlined className="header-icon" />
          <span className="header-title">待办</span>
          <span className="header-progress">{progress.completed}/{progress.total}</span>
        </div>
        <div className="header-expand">
          {expanded ? <UpOutlined /> : <DownOutlined />}
        </div>
      </div>

      {expanded && (
        <div className="todolist-items">
          {items.map((item) => (
            <div
              key={item.id}
              className={`todo-item ${isCompleted(item.status) ? 'completed' : ''}`}
            >
              <div className={`todo-checkbox ${isCompleted(item.status) ? 'checked' : ''}`}>
                {isCompleted(item.status) && <span className="checkmark">✓</span>}
              </div>
              <span className={`todo-title ${isCompleted(item.status) ? 'completed' : ''}`}>
                {item.title}
              </span>
            </div>
          ))}

          {items.length === 0 && (
            <div className="todolist-empty">
              <span>暂无任务</span>
            </div>
          )}
        </div>
      )}
    </VisTodoListWrap>
  );
};

export default VisTodoList;
