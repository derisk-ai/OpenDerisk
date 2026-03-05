/**
 * Interaction Components - Unified Tool Authorization System
 *
 * Export all interaction-related components for easy import.
 */

// Context and Provider
export {
  InteractionProvider,
  InteractionContext,
  useInteraction,
  usePendingRequests,
  useAuthorizationRequests,
  useInteractionConnection,
  type InteractionProviderProps,
  type InteractionState,
  type InteractionActions,
  type InteractionContextValue,
} from './InteractionManager';

// Authorization Dialog
export {
  AuthorizationDialog,
  type AuthorizationDialogProps,
} from './AuthorizationDialog';

// Interaction Handler
export {
  InteractionHandler,
  type InteractionHandlerProps,
} from './InteractionHandler';
