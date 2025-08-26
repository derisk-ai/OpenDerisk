import React from 'react';
import { ErrorBoundary } from 'react-error-boundary';

export function Fallback({ data }: any) {
  console.log('errorData', data)

  return (
    <div role="alert">
      <p>Something went wrong:</p>
      <pre style={{ color: 'red' }}>{data?.message}</pre>
    </div>
  );
}

export default ErrorBoundary;
