import EditChannelClient from './edit-channel-client';

export function generateStaticParams() {
  return [{ id: 'placeholder' }];
}

export default function EditChannelPage() {
  return <EditChannelClient />;
}