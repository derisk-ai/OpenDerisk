import { DELETE, GET, POST, PATCH } from '../index';

// Types
export type RiskLevel = 'green' | 'blue' | 'yellow' | 'red';

export interface EntityType {
  id: string;
  name: string;
  description?: string;
  defaultSkillCode?: string;
  icon?: string;
  createdAt?: string;
  entityCount?: number;
}

export interface EntityTypeCreate {
  id?: string;
  name: string;
  description?: string;
  defaultSkillCode?: string;
  icon?: string;
}

export interface Entity {
  id: string;
  typeId: string;
  typeName?: string;
  name: string;
  config?: Record<string, any>;
  extraSkills?: string[];
  source?: string;
  createdAt?: string;
  updatedAt?: string;
  riskLevel?: RiskLevel;
  riskLevelText?: string;
  lastCheckAt?: string;
  summary?: string;
  subscribed?: boolean;
}

export interface EntityCreate {
  id?: string;
  typeId: string;
  name: string;
  config?: Record<string, any>;
  extraSkills?: string[];
  source?: string;
}

export interface EntityRelation {
  id: string;
  sourceEntityId: string;
  sourceEntityName?: string;
  targetEntityId: string;
  targetEntityName?: string;
  relationType: 'depends_on' | 'contains' | 'impacts';
  strength: 'strong' | 'weak';
  createdAt?: string;
}

export interface EntityRelationCreate {
  id?: string;
  sourceEntityId: string;
  targetEntityId: string;
  relationType: string;
  strength?: string;
}

export interface RiskCheckRecord {
  id: string;
  entityId: string;
  convId?: string;
  riskLevel: RiskLevel;
  summary?: string;
  details?: Record<string, any>;
  suggestions?: Array<{ action: string; auto: boolean }>;
  checkedAt?: string;
}

export interface EntitySubscription {
  id: string;
  userId: string;
  entityId: string;
  entityName?: string;
  entityTypeName?: string;
  riskLevel?: RiskLevel;
  notifyLevel: 'all' | 'yellow_plus' | 'red_only';
  notifyChannels?: string[];
  createdAt?: string;
}

export interface EntitySubscriptionCreate {
  id?: string;
  userId: string;
  entityId: string;
  notifyLevel?: string;
  notifyChannels?: string[];
}

export interface RiskSummary {
  greenCount: number;
  blueCount: number;
  yellowCount: number;
  redCount: number;
  totalCount: number;
}

export interface HeatmapDataPoint {
  date: string;
  greenCount: number;
  blueCount: number;
  yellowCount: number;
  redCount: number;
}

export interface HeatmapResponse {
  data: HeatmapDataPoint[];
}

// API endpoints
const API_PREFIX = '/api/v1/serve/risk_dashboard';

// ============ Dashboard Summary ============

/**
 * Get risk summary for all entities
 */
export const getRiskSummary = () => {
  return GET<{}, RiskSummary>(`${API_PREFIX}/summary`);
};

/**
 * Get heatmap data
 */
export const getHeatmapData = (days: number = 30) => {
  return GET<{ days: number }, HeatmapResponse>(`${API_PREFIX}/heatmap`, { days });
};

// ============ Entity Types ============

/**
 * List all entity types
 */
export const getEntityTypes = () => {
  return GET<{}, EntityType[]>(`${API_PREFIX}/entity-types`);
};

/**
 * Get a specific entity type
 */
export const getEntityType = (typeId: string) => {
  return GET<{}, EntityType>(`${API_PREFIX}/entity-types/${typeId}`);
};

/**
 * Create a new entity type
 */
export const createEntityType = (data: EntityTypeCreate) => {
  return POST<EntityTypeCreate, EntityType>(`${API_PREFIX}/entity-types`, data);
};

/**
 * Delete an entity type
 */
export const deleteEntityType = (typeId: string) => {
  return DELETE<{}, null>(`${API_PREFIX}/entity-types/${typeId}`);
};

// ============ Entities ============

/**
 * List entities with optional filters
 */
export const getEntities = (params?: {
  typeId?: string;
  riskLevel?: string;
  userId?: string;
}) => {
  return GET<typeof params, Entity[]>(`${API_PREFIX}/entities`, params);
};

/**
 * Get a specific entity
 */
export const getEntity = (entityId: string) => {
  return GET<{}, Entity>(`${API_PREFIX}/entities/${entityId}`);
};

/**
 * Create a new entity
 */
export const createEntity = (data: EntityCreate) => {
  return POST<EntityCreate, Entity>(`${API_PREFIX}/entities`, data);
};

/**
 * Update an entity
 */
export const updateEntity = (entityId: string, data: Partial<EntityCreate>) => {
  return PATCH<Partial<EntityCreate>, Entity>(`${API_PREFIX}/entities/${entityId}`, data);
};

/**
 * Delete an entity
 */
export const deleteEntity = (entityId: string) => {
  return DELETE<{}, null>(`${API_PREFIX}/entities/${entityId}`);
};

/**
 * Trigger a risk check for an entity
 */
export const triggerEntityCheck = (entityId: string) => {
  return POST<{}, RiskCheckRecord>(`${API_PREFIX}/entities/${entityId}/check`);
};

/**
 * Get check history for an entity
 */
export const getEntityCheckHistory = (entityId: string, limit: number = 10) => {
  return GET<{ limit: number }, RiskCheckRecord[]>(
    `${API_PREFIX}/entities/${entityId}/history`,
    { limit }
  );
};

/**
 * Get entity relations
 */
export const getEntityRelations = (entityId: string) => {
  return GET<{}, EntityRelation[]>(`${API_PREFIX}/entities/${entityId}/relations`);
};

// ============ Relations ============

/**
 * Create an entity relation
 */
export const createEntityRelation = (data: EntityRelationCreate) => {
  return POST<EntityRelationCreate, EntityRelation>(`${API_PREFIX}/relations`, data);
};

/**
 * Delete an entity relation
 */
export const deleteEntityRelation = (relationId: string) => {
  return DELETE<{}, null>(`${API_PREFIX}/relations/${relationId}`);
};

// ============ Subscriptions ============

/**
 * List subscriptions for a user
 */
export const getSubscriptions = (userId: string) => {
  return GET<{ userId: string }, EntitySubscription[]>(`${API_PREFIX}/subscriptions`, {
    userId,
  });
};

/**
 * Create a subscription
 */
export const createSubscription = (data: EntitySubscriptionCreate) => {
  return POST<EntitySubscriptionCreate, EntitySubscription>(
    `${API_PREFIX}/subscriptions`,
    data
  );
};

/**
 * Delete a subscription
 */
export const deleteSubscription = (subscriptionId: string) => {
  return DELETE<{}, null>(`${API_PREFIX}/subscriptions/${subscriptionId}`);
};