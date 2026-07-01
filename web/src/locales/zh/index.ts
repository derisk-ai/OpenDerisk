import { ChatZh } from './chat';
import { CommonZh } from './common';
import { FlowZn } from './flow';
import { PermissionsZh } from './permissions';
import { WorkspacesZh } from './workspaces';

const zh = {
  ...ChatZh,
  ...FlowZn,
  ...CommonZh,
  ...PermissionsZh,
  ...WorkspacesZh,
};

export default zh;
