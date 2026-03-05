/**
 * 统一会话服务
 * 
 * 提供统一的会话管理接口，支持V1/V2 Agent的透明会话管理
 */

import { GET, POST } from '@/client/api';

/**
 * 统一消息模型
 */
export interface UnifiedMessage {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  timestamp: Date;
  metadata?: Record<string, any>;
}

/**
 * 统一会话实例
 */
export interface UnifiedSession {
  sessionId: string;
  convId: string;
  appCode: string;
  userId?: string;
  agentVersion: 'v1' | 'v2';
  createdAt: Date;
  updatedAt: Date;
  messageCount: number;
  history: UnifiedMessage[];
  metadata?: Record<string, any>;
}

/**
 * 创建会话请求
 */
interface CreateSessionRequest {
  app_code: string;
  user_id?: string;
  agent_version?: 'v1' | 'v2';
}

/**
 * 创建会话响应
 */
interface CreateSessionResponse {
  session_id: string;
  conv_id: string;
  app_code: string;
  agent_version: string;
}

/**
 * 统一会话服务类
 */
export class UnifiedSessionService {
  private sessionCache: Map<string, UnifiedSession> = new Map();
  private convToSession: Map<string, string> = new Map();

  /**
   * 创建或获取会话
   * 
   * @param appCode 应用代码
   * @param agentVersion Agent版本
   * @param userId 用户ID
   */
  async getOrCreateSession(
    appCode: string,
    agentVersion: 'v1' | 'v2' = 'v2',
    userId?: string
  ): Promise<UnifiedSession> {
    const cacheKey = `${appCode}_${agentVersion}`;

    if (this.sessionCache.has(cacheKey)) {
      const session = this.sessionCache.get(cacheKey)!;
      session.history = await this.loadHistory(session.sessionId, agentVersion);
      return session;
    }

    const response = await POST<CreateSessionRequest, CreateSessionResponse>(
      '/api/unified/session/create',
      {
        app_code: appCode,
        user_id: userId,
        agent_version: agentVersion
      }
    );

    const session: UnifiedSession = {
      sessionId: response.session_id,
      convId: response.conv_id,
      appCode: appCode,
      userId: userId,
      agentVersion: agentVersion,
      createdAt: new Date(),
      updatedAt: new Date(),
      messageCount: 0,
      history: await this.loadHistory(response.session_id, agentVersion)
    };

    this.sessionCache.set(cacheKey, session);
    this.convToSession.set(response.conv_id, response.session_id);

    return session;
  }

  /**
   * 获取会话
   */
  async getSession(sessionId?: string, convId?: string): Promise<UnifiedSession | null> {
    if (sessionId) {
      const cacheKey = Array.from(this.sessionCache.keys()).find(key => 
        this.sessionCache.get(key)?.sessionId === sessionId
      );
      return cacheKey ? this.sessionCache.get(cacheKey)! : null;
    }

    if (convId) {
      const sid = this.convToSession.get(convId);
      if (sid) {
        const cacheKey = Array.from(this.sessionCache.keys()).find(key =>
          this.sessionCache.get(key)?.sessionId === sid
        );
        return cacheKey ? this.sessionCache.get(cacheKey)! : null;
      }
    }

    return null;
  }

  /**
   * 加载历史消息（自动适配V1/V2）
   */
  async loadHistory(
    sessionId: string,
    agentVersion: 'v1' | 'v2'
  ): Promise<UnifiedMessage[]> {
    try {
      const endpoint = agentVersion === 'v2'
        ? `/api/unified/session/${sessionId}/history`
        : `/api/conversation/${sessionId}/messages`;

      const messages = await GET<any, any[]>(endpoint);

      return messages.map(msg => this._normalizeMessage(msg, agentVersion));
    } catch (error) {
      console.error('[UnifiedSessionService] 加载历史消息失败:', error);
      return [];
    }
  }

  /**
   * 添加消息到会话
   */
  async addMessage(
    sessionId: string,
    role: 'user' | 'assistant' | 'system' | 'tool',
    content: string,
    metadata?: Record<string, any>
  ): Promise<UnifiedMessage> {
    const cacheKey = Array.from(this.sessionCache.keys()).find(key =>
      this.sessionCache.get(key)?.sessionId === sessionId
    );

    if (!cacheKey) {
      throw new Error(`会话不存在: ${sessionId}`);
    }

    const session = this.sessionCache.get(cacheKey)!;
    const message: UnifiedMessage = {
      id: this._generateMessageId(),
      role,
      content,
      timestamp: new Date(),
      metadata: {
        agentVersion: session.agentVersion,
        ...metadata
      }
    };

    session.history.push(message);
    session.messageCount++;
    session.updatedAt = new Date();

    await POST('/api/unified/session/message', {
      session_id: sessionId,
      role,
      content,
      metadata
    });

    return message;
  }

  /**
   * 关闭会话
   */
  async closeSession(sessionId: string): Promise<void> {
    const cacheKey = Array.from(this.sessionCache.keys()).find(key =>
      this.sessionCache.get(key)?.sessionId === sessionId
    );

    if (!cacheKey) return;

    const session = this.sessionCache.get(cacheKey)!;

    try {
      await POST('/api/unified/session/close', {
        session_id: sessionId
      });
    } catch (error) {
      console.error('[UnifiedSessionService] 关闭会话失败:', error);
    }

    this.sessionCache.delete(cacheKey);
    this.convToSession.delete(session.convId);
  }

  /**
   * 标准化消息格式
   */
  private _normalizeMessage(msg: any, version: 'v1' | 'v2'): UnifiedMessage {
    return {
      id: msg.message_id || msg.id || this._generateMessageId(),
      role: msg.role || msg.type || 'user',
      content: msg.content || msg.context || '',
      timestamp: new Date(msg.timestamp || msg.time_stamp || msg.created_at || Date.now()),
      metadata: {
        version,
        roundIndex: msg.round_index || msg.rounds,
        ...msg.metadata
      }
    };
  }

  /**
   * 生成消息ID
   */
  private _generateMessageId(): string {
    return `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * 清理缓存
   */
  clearCache() {
    this.sessionCache.clear();
    this.convToSession.clear();
  }
}

// 单例实例
let unifiedSessionServiceInstance: UnifiedSessionService | null = null;

/**
 * 获取统一会话服务实例
 */
export function getUnifiedSessionService(): UnifiedSessionService {
  if (!unifiedSessionServiceInstance) {
    unifiedSessionServiceInstance = new UnifiedSessionService();
  }
  return unifiedSessionServiceInstance;
}