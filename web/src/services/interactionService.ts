/**
 * Interaction Service - Unified Tool Authorization System
 *
 * Client-side service for managing user interactions with the backend.
 * Handles WebSocket connections, HTTP polling, and interaction state.
 */

import { GET, POST } from '@/client/api';
import type {
  InteractionRequest,
  InteractionResponse,
  InteractionStatus,
  GrantScope,
} from '@/types/interaction';
import { InteractionStatus as InteractionStatusEnum, GrantScope as GrantScopeEnum } from '@/types/interaction';

// ========== Types ==========

/**
 * Connection state for the interaction service.
 */
export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

/**
 * WebSocket message types from the server.
 */
export interface WebSocketMessage {
  type: 'interaction_request' | 'interaction_update' | 'connection_ack' | 'error';
  request?: InteractionRequest;
  update?: Partial<InteractionRequest>;
  error?: string;
  timestamp: string;
}

/**
 * Event handlers for the interaction service.
 */
export interface InteractionEventHandlers {
  /** Called when a new interaction request is received */
  onRequest?: (request: InteractionRequest) => void;
  /** Called when a request is updated */
  onRequestUpdate?: (requestId: string, update: Partial<InteractionRequest>) => void;
  /** Called when connection state changes */
  onConnectionStateChange?: (state: ConnectionState) => void;
  /** Called when an error occurs */
  onError?: (error: Error) => void;
}

/**
 * Configuration for the interaction service.
 */
export interface InteractionServiceConfig {
  /** WebSocket endpoint URL */
  wsEndpoint?: string;
  /** HTTP polling endpoint URL */
  httpEndpoint?: string;
  /** Polling interval in milliseconds (if using HTTP polling) */
  pollingInterval?: number;
  /** Auto-reconnect on disconnect */
  autoReconnect?: boolean;
  /** Max reconnection attempts */
  maxReconnectAttempts?: number;
  /** Session ID for filtering requests */
  sessionId?: string;
}

// ========== Interaction Service Class ==========

/**
 * InteractionService - Manages communication with the interaction gateway.
 *
 * Supports both WebSocket (preferred) and HTTP polling fallback.
 */
export class InteractionService {
  private config: Required<InteractionServiceConfig>;
  private handlers: InteractionEventHandlers;
  private ws: WebSocket | null = null;
  private connectionState: ConnectionState = 'disconnected';
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pollingTimer: ReturnType<typeof setInterval> | null = null;
  private pendingRequests: Map<string, InteractionRequest> = new Map();
  private usePolling = false;

  constructor(
    config: InteractionServiceConfig = {},
    handlers: InteractionEventHandlers = {},
  ) {
    this.config = {
      wsEndpoint: config.wsEndpoint || `${this.getWsBaseUrl()}/api/v1/interaction/ws`,
      httpEndpoint: config.httpEndpoint || '/api/v1/interaction',
      pollingInterval: config.pollingInterval || 2000,
      autoReconnect: config.autoReconnect ?? true,
      maxReconnectAttempts: config.maxReconnectAttempts || 5,
      sessionId: config.sessionId || '',
    };
    this.handlers = handlers;
  }

  // ========== Connection Management ==========

  /**
   * Connect to the interaction gateway.
   *
   * Attempts WebSocket first, falls back to HTTP polling.
   */
  async connect(): Promise<void> {
    if (this.connectionState === 'connected' || this.connectionState === 'connecting') {
      return;
    }

    this.setConnectionState('connecting');

    try {
      // Try WebSocket first
      await this.connectWebSocket();
    } catch (error) {
      console.warn('WebSocket connection failed, falling back to HTTP polling:', error);
      this.usePolling = true;
      await this.startPolling();
    }
  }

  /**
   * Disconnect from the interaction gateway.
   */
  disconnect(): void {
    this.stopReconnect();
    this.stopPolling();

    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }

    this.setConnectionState('disconnected');
  }

  /**
   * Get the current connection state.
   */
  getConnectionState(): ConnectionState {
    return this.connectionState;
  }

  /**
   * Check if connected.
   */
  isConnected(): boolean {
    return this.connectionState === 'connected';
  }

  // ========== Request Management ==========

  /**
   * Get all pending interaction requests.
   */
  getPendingRequests(): InteractionRequest[] {
    return Array.from(this.pendingRequests.values());
  }

  /**
   * Get a specific pending request.
   */
  getPendingRequest(requestId: string): InteractionRequest | undefined {
    return this.pendingRequests.get(requestId);
  }

  /**
   * Fetch pending requests from the server.
   */
  async fetchPendingRequests(sessionId?: string): Promise<InteractionRequest[]> {
    try {
      const response = await GET<
        { session_id?: string },
        { requests: InteractionRequest[] }
      >(
        `${this.config.httpEndpoint}/pending`,
        { session_id: sessionId || this.config.sessionId },
      );

      if (response.data.success && response.data.data) {
        const requests = response.data.data.requests || [];
        // Update local cache
        requests.forEach(req => this.pendingRequests.set(req.request_id, req));
        return requests;
      }

      return [];
    } catch (error) {
      console.error('Failed to fetch pending requests:', error);
      this.handlers.onError?.(error as Error);
      return [];
    }
  }

  // ========== Response Submission ==========

  /**
   * Submit a response to an interaction request.
   */
  async submitResponse(response: Partial<InteractionResponse>): Promise<boolean> {
    if (!response.request_id) {
      throw new Error('Response must include request_id');
    }

    try {
      const fullResponse: InteractionResponse = {
        request_id: response.request_id,
        session_id: response.session_id || this.config.sessionId,
        choice: response.choice,
        choices: response.choices || [],
        input_value: response.input_value,
        file_ids: response.file_ids || [],
        status: response.status || InteractionStatusEnum.RESPONDED,
        user_message: response.user_message,
        cancel_reason: response.cancel_reason,
        grant_scope: response.grant_scope,
        grant_duration: response.grant_duration,
        metadata: response.metadata || {},
        timestamp: new Date().toISOString(),
      };

      const result = await POST<InteractionResponse, { success: boolean }>(
        `${this.config.httpEndpoint}/respond`,
        fullResponse,
      );

      if (result.data.success) {
        // Remove from pending requests
        this.pendingRequests.delete(response.request_id);
        return true;
      }

      return false;
    } catch (error) {
      console.error('Failed to submit response:', error);
      this.handlers.onError?.(error as Error);
      return false;
    }
  }

  /**
   * Submit a simple confirmation response.
   */
  async confirm(requestId: string, confirmed: boolean, grantScope?: GrantScope): Promise<boolean> {
    return this.submitResponse({
      request_id: requestId,
      choice: confirmed ? 'yes' : 'no',
      status: InteractionStatusEnum.RESPONDED,
      grant_scope: grantScope,
    });
  }

  /**
   * Submit an authorization response.
   */
  async authorizeToolExecution(
    requestId: string,
    allow: boolean,
    grantScope: GrantScope = GrantScopeEnum.ONCE,
  ): Promise<boolean> {
    return this.submitResponse({
      request_id: requestId,
      choice: allow ? 'allow' : 'deny',
      status: InteractionStatusEnum.RESPONDED,
      grant_scope: allow ? grantScope : undefined,
    });
  }

  /**
   * Submit a text input response.
   */
  async submitTextInput(requestId: string, value: string): Promise<boolean> {
    return this.submitResponse({
      request_id: requestId,
      input_value: value,
      status: InteractionStatusEnum.RESPONDED,
    });
  }

  /**
   * Submit a selection response.
   */
  async submitSelection(requestId: string, choices: string | string[]): Promise<boolean> {
    const choiceArray = Array.isArray(choices) ? choices : [choices];
    return this.submitResponse({
      request_id: requestId,
      choice: choiceArray[0],
      choices: choiceArray,
      status: InteractionStatusEnum.RESPONDED,
    });
  }

  /**
   * Cancel/skip an interaction request.
   */
  async cancelRequest(requestId: string, reason?: string): Promise<boolean> {
    return this.submitResponse({
      request_id: requestId,
      status: InteractionStatusEnum.CANCELLED,
      cancel_reason: reason,
    });
  }

  /**
   * Skip an interaction request.
   */
  async skipRequest(requestId: string): Promise<boolean> {
    return this.submitResponse({
      request_id: requestId,
      status: InteractionStatusEnum.SKIPPED,
    });
  }

  /**
   * Defer an interaction request.
   */
  async deferRequest(requestId: string): Promise<boolean> {
    return this.submitResponse({
      request_id: requestId,
      status: InteractionStatusEnum.DEFERRED,
    });
  }

  // ========== Internal: WebSocket ==========

  private async connectWebSocket(): Promise<void> {
    return new Promise((resolve, reject) => {
      const url = this.config.sessionId
        ? `${this.config.wsEndpoint}?session_id=${encodeURIComponent(this.config.sessionId)}`
        : this.config.wsEndpoint;

      this.ws = new WebSocket(url);

      const timeout = setTimeout(() => {
        this.ws?.close();
        reject(new Error('WebSocket connection timeout'));
      }, 10000);

      this.ws.onopen = () => {
        clearTimeout(timeout);
        this.reconnectAttempts = 0;
        this.setConnectionState('connected');
        resolve();
      };

      this.ws.onmessage = (event) => {
        this.handleWebSocketMessage(event);
      };

      this.ws.onerror = (event) => {
        clearTimeout(timeout);
        console.error('WebSocket error:', event);
        reject(new Error('WebSocket connection error'));
      };

      this.ws.onclose = (event) => {
        clearTimeout(timeout);
        this.handleWebSocketClose(event);
      };
    });
  }

  private handleWebSocketMessage(event: MessageEvent): void {
    try {
      const message = JSON.parse(event.data) as WebSocketMessage;

      switch (message.type) {
        case 'interaction_request':
          if (message.request) {
            this.pendingRequests.set(message.request.request_id, message.request);
            this.handlers.onRequest?.(message.request);
          }
          break;

        case 'interaction_update':
          if (message.update && message.update.request_id) {
            const existing = this.pendingRequests.get(message.update.request_id as string);
            if (existing) {
              const updated = { ...existing, ...message.update };
              this.pendingRequests.set(existing.request_id, updated);
              this.handlers.onRequestUpdate?.(existing.request_id, message.update);
            }
          }
          break;

        case 'connection_ack':
          // Connection acknowledged
          break;

        case 'error':
          console.error('Server error:', message.error);
          this.handlers.onError?.(new Error(message.error || 'Unknown server error'));
          break;
      }
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error);
    }
  }

  private handleWebSocketClose(event: CloseEvent): void {
    this.ws = null;

    if (event.code !== 1000 && this.config.autoReconnect) {
      this.setConnectionState('reconnecting');
      this.scheduleReconnect();
    } else {
      this.setConnectionState('disconnected');
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.config.maxReconnectAttempts) {
      console.warn('Max reconnection attempts reached, falling back to polling');
      this.usePolling = true;
      this.startPolling();
      return;
    }

    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    this.reconnectAttempts++;

    this.reconnectTimer = setTimeout(async () => {
      try {
        await this.connectWebSocket();
      } catch {
        this.scheduleReconnect();
      }
    }, delay);
  }

  private stopReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.reconnectAttempts = 0;
  }

  // ========== Internal: HTTP Polling ==========

  private async startPolling(): Promise<void> {
    this.setConnectionState('connected');

    // Fetch initial requests
    await this.fetchPendingRequests();

    // Start polling
    this.pollingTimer = setInterval(async () => {
      const requests = await this.fetchPendingRequests();

      // Notify about new requests
      requests.forEach(req => {
        if (!this.pendingRequests.has(req.request_id)) {
          this.handlers.onRequest?.(req);
        }
        this.pendingRequests.set(req.request_id, req);
      });
    }, this.config.pollingInterval);
  }

  private stopPolling(): void {
    if (this.pollingTimer) {
      clearInterval(this.pollingTimer);
      this.pollingTimer = null;
    }
  }

  // ========== Internal: Helpers ==========

  private setConnectionState(state: ConnectionState): void {
    if (this.connectionState !== state) {
      this.connectionState = state;
      this.handlers.onConnectionStateChange?.(state);
    }
  }

  private getWsBaseUrl(): string {
    if (typeof window === 'undefined') {
      // SSR context: use env var or default to relative path
      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL;
      if (apiBase) {
        const url = new URL(apiBase);
        const protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${url.host}`;
      }
      return 'ws://127.0.0.1:7777';
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = process.env.NEXT_PUBLIC_API_BASE_URL
      ? new URL(process.env.NEXT_PUBLIC_API_BASE_URL).host
      : window.location.host;

    return `${protocol}//${host}`;
  }

  /**
   * Update event handlers.
   */
  setHandlers(handlers: InteractionEventHandlers): void {
    this.handlers = { ...this.handlers, ...handlers };
  }

  /**
   * Update session ID and refetch pending requests.
   */
  async setSessionId(sessionId: string): Promise<void> {
    this.config.sessionId = sessionId;
    this.pendingRequests.clear();

    // Reconnect with new session if using WebSocket
    if (!this.usePolling && this.ws) {
      this.disconnect();
      await this.connect();
    } else {
      await this.fetchPendingRequests();
    }
  }
}

// ========== Singleton Instance ==========

let serviceInstance: InteractionService | null = null;

/**
 * Get the global interaction service instance.
 */
export function getInteractionService(
  config?: InteractionServiceConfig,
  handlers?: InteractionEventHandlers,
): InteractionService {
  if (!serviceInstance) {
    serviceInstance = new InteractionService(config, handlers);
  }
  return serviceInstance;
}

/**
 * Reset the global interaction service instance.
 */
export function resetInteractionService(): void {
  if (serviceInstance) {
    serviceInstance.disconnect();
    serviceInstance = null;
  }
}

// ========== React Hook Helper ==========

/**
 * Create configuration for use with React hooks.
 */
export function createInteractionServiceConfig(
  sessionId?: string,
): InteractionServiceConfig {
  return {
    sessionId,
    autoReconnect: true,
    maxReconnectAttempts: 5,
    pollingInterval: 2000,
  };
}

export default InteractionService;
