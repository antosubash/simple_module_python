import { usePage } from '@inertiajs/react';
import { PageShell } from '@ui/components/PageShell';
import { AuthenticatedLayout } from '@ui/layouts/AuthenticatedLayout';

interface Props {
  welcome: string;
}

function Home() {
  const { welcome } = usePage<{ props: Props }>().props as unknown as Props;

  return (
    <PageShell title="Dashboard" description="Overview of your application">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <StatCard title="Products" value="-" color="primary" />
        <StatCard title="Users" value="-" color="success" />
        <StatCard title="Modules" value="3" color="purple" />
      </div>

      <div className="card p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">Welcome</h2>
        <p className="text-gray-600">{welcome}</p>
        <p className="mt-4 text-sm text-gray-500">
          This is a modular monolith built with FastAPI, Inertia.js, and React. Each module provides
          its own pages, API endpoints, and database schema.
        </p>
      </div>
    </PageShell>
  );
}

function StatCard({ title, value, color }: { title: string; value: string; color: string }) {
  const colorMap: Record<string, string> = {
    primary: 'bg-primary-50 border-primary-200 text-primary-600',
    success: 'bg-green-50 border-green-200 text-green-600',
    purple: 'bg-purple-50 border-purple-200 text-purple-600',
  };
  const valueColorMap: Record<string, string> = {
    primary: 'text-primary-900',
    success: 'text-green-900',
    purple: 'text-purple-900',
  };

  return (
    <div className={`rounded-xl border p-5 ${colorMap[color]}`}>
      <h3 className="text-sm font-medium">{title}</h3>
      <p className={`text-3xl font-bold mt-2 ${valueColorMap[color]}`}>{value}</p>
    </div>
  );
}

Home.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Home;
