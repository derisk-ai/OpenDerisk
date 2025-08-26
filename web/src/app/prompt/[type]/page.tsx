import AddOrEditPrompt from './prompt';

export async function generateStaticParams() {
  return [
    { type: 'add' },
    { type: 'edit' }
  ];
}

export default function Page() {
  return <AddOrEditPrompt />;
}
