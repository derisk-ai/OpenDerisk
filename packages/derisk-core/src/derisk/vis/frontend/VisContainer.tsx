/**
 * VIS容器组件 - 管理Part列表和实时更新
 */

import React, { useEffect, useState, useCallback } from 'react';
import PartRenderer from './PartRenderer';
import type { Part, WSMessage } from './types';
import './vis-container.css';

interface VisContainerProps {
  convId: string;
  wsUrl?: string;
  initialParts?: Part[];
}

export const VisContainer: React.FC<VisContainerProps> = ({ 
  convId, 
  wsUrl,
  initialParts = [] 
}) => {
  const [parts, setParts] = useState<Part[]>(initialParts);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // WebSocket连接
  useEffect(() => {
    if (!wsUrl) return;
    
    const ws = new WebSocket(`${wsUrl}/ws/${convId}`);
    
    ws.onopen = () => {
      setConnected(true);
      setError(null);
      console.log('[VIS] WebSocket connected');
    };
    
    ws.onmessage = (event) => {
      try {
        const message: WSMessage = JSON.parse(event.data);
        handleMessage(message);
      } catch (e) {
        console.error('[VIS] Failed to parse message:', e);
      }
    };
    
    ws.onerror = (e) => {
      console.error('[VIS] WebSocket error:', e);
      setError('WebSocket connection error');
    };
    
    ws.onclose = () => {
      setConnected(false);
      console.log('[VIS] WebSocket disconnected');
    };
    
    return () => {
      ws.close();
    };
  }, [wsUrl, convId]);
  
  // 处理WebSocket消息
  const handleMessage = useCallback((message: WSMessage) => {
    if (message.type === 'part_update') {
      const part = message.data as Part;
      
      setParts(prevParts => {
        // 查找是否已存在相同UID的Part
        const existingIndex = prevParts.findIndex(p => p.uid === part.uid);
        
        if (existingIndex >= 0) {
          // 更新现有Part
          const updatedParts = [...prevParts];
          
          // 增量更新逻辑
          if (part.type === 'incr') {
            // 追加内容
            const oldPart = updatedParts[existingIndex];
            updatedParts[existingIndex] = {
              ...oldPart,
              ...part,
              content: oldPart.content + (part.content || ''),
            };
          } else {
            // 全量替换
            updatedParts[existingIndex] = part;
          }
          
          return updatedParts;
        } else {
          // 添加新Part
          return [...prevParts, part];
        }
      });
    }
  }, []);
  
  // 手动添加Part(用于测试)
  const addPart = useCallback((part: Part) => {
    setParts(prev => [...prev, part]);
  }, []);
  
  // 清空所有Part
  const clearParts = useCallback(() => {
    setParts([]);
  }, []);
  
  return (
    <div className="vis-container">
      {/* 连接状态指示器 */}
      <div className="connection-status">
        <span className={`status-dot ${connected ? 'connected' : 'disconnected'}`} />
        <span>{connected ? 'Connected' : 'Disconnected'}</span>
        {error && <span className="error">{error}</span>}
      </div>
      
      {/* Part列表 */}
      <div className="parts-list">
        {parts.map((part, index) => (
          <div key={part.uid || index} className="part-wrapper">
            <PartRenderer part={part} />
          </div>
        ))}
      </div>
      
      {/* 空状态 */}
      {parts.length === 0 && (
        <div className="empty-state">
          <p>No content yet. Waiting for agent response...</p>
        </div>
      )}
    </div>
  );
};

export default VisContainer;