import { POST, GET } from '..';

export const createDelivery = (data: any) => POST('/api/v1/serve_delivery_service/deliveries/create', data);
export const listDeliveries = (data: any) => POST('/api/v1/serve_delivery_service/deliveries/list', data);
export const getDeliveryInfo = (delivery_id: number) => GET(`/api/v1/serve_delivery_service/deliveries/info?delivery_id=${delivery_id}`);
export const sendDelivery = (delivery_id: number) => POST(`/api/v1/serve_delivery_service/deliveries/${delivery_id}/send`, {});
