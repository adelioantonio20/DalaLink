import React from 'react';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { AuthPortal } from './apps/auth/AuthPortal';
import { PassengerApp } from './apps/passenger/PassengerApp';
import { DriverApp } from './apps/driver/DriverApp';
import { AdminDashboard } from './apps/admin/AdminDashboard';
import { CorporatePortal } from './apps/corporate/CorporatePortal';

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

  switch (user.role) {
    case 'DRIVER':
      return <DriverApp />;
    case 'ADMIN':
      return <AdminDashboard />;
    case 'COMPANY_ADMIN':
    case 'EMPLOYEE':
      return <CorporatePortal />;
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
