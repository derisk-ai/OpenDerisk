import { POST, GET } from '..';

export const createIntervention = (data: any) => POST('/api/v1/serve_intervention_service/interventions/create', data);
export const listInterventions = (data: any) => POST('/api/v1/serve_intervention_service/interventions/list', data);
export const getInterventionInfo = (intervention_id: number) => GET(`/api/v1/serve_intervention_service/interventions/info?intervention_id=${intervention_id}`);
export const resolveIntervention = (intervention_id: number, data: any) => POST(`/api/v1/serve_intervention_service/interventions/${intervention_id}/resolve`, data);
export const abortIntervention = (intervention_id: number) => POST(`/api/v1/serve_intervention_service/interventions/${intervention_id}/abort`, {});
