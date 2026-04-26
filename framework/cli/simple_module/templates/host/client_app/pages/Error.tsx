type ErrorProps = {
  status: number;
  message?: string;
};

export default function Error({ status, message }: ErrorProps) {
  return (
    <main style={{ padding: '2rem', maxWidth: '40rem', margin: '0 auto' }}>
      <h1>{status}</h1>
      <p>{message || 'Something went wrong.'}</p>
    </main>
  );
}
