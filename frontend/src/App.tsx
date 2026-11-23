import React from 'react';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { AuthPortal } from './apps/auth/AuthPortal';
import { PassengerApp } from './apps/passenger/PassengerApp';
import { DriverApp } from './apps/driver/DriverApp';
import { AdminDashboard } from './apps/admin/AdminDashboard';

const PortalRouter: React.FC = () => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm font-semibold text-slate-600">
        A carregar DalaLink Luanda...
      </div>
    );
  }

  if (!user) {
    return <AuthPortal />;
  }

  // Active MVP environments: Passenger, Driver, and Admin/Field Collector.
  // Legacy financial/corporate/owner portals are preserved in repo but excluded from active MVP navigation.
  switch (user.role) {
    case 'DRIVER':
      return <DriverApp />;
    case 'ADMIN':
    case 'FIELD_COLLECTOR':
      return <AdminDashboard />;
    case 'PASSENGER':
    default:
      return <PassengerApp />;
  }
};

export default function App() {
  return (
    <AuthProvider>
      <PortalRouter />
    </AuthProvider>
  );
}
