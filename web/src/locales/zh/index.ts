import { ChatZh } from './chat';
import { CommonZh } from './common';
import { FlowZn } from './flow';
import { PermissionsZh } from './permissions';

const zh = {
  ...ChatZh,
  ...FlowZn,
  ...CommonZh,
  ...PermissionsZh,
};

export default zh;
