'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronLeft, Cpu, LayoutDashboard, LogOut, Rocket, ScrollText } from 'lucide-react';
import { cn } from '@/lib/shadcn/utils';

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const NAV_ITEMS: NavItem[] = [
  { href: '/admin/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/admin/profiles', label: 'Profiles', icon: Cpu },
  { href: '/admin/sessions', label: 'Sessions', icon: ScrollText },
  { href: '/admin/deploy', label: 'Deploy', icon: Rocket },
];

interface AdminSidebarProps {
  onLogout: () => void;
}

export function AdminSidebar({ onLogout }: AdminSidebarProps) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        'bg-sidebar border-sidebar-border flex h-screen flex-col border-r transition-[width] duration-200 ease-out motion-reduce:transition-none',
        collapsed ? 'w-[52px]' : 'w-[220px]'
      )}
    >
      {/* Brand */}
      <div
        className={cn(
          'border-sidebar-border flex h-14 items-center border-b px-3',
          collapsed ? 'justify-center' : 'gap-2.5'
        )}
      >
        {!collapsed && (
          <span className="text-sidebar-foreground truncate font-mono text-xs font-bold tracking-wider uppercase">
            Agent Admin
          </span>
        )}
        {collapsed && (
          <span className="text-sidebar-foreground font-mono text-xs font-bold">A</span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-2 py-3">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-label={collapsed ? item.label : undefined}
              title={collapsed ? item.label : undefined}
              className={cn(
                'group flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                  : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground'
              )}
            >
              <item.icon
                aria-hidden="true"
                className={cn(
                  'size-4 shrink-0',
                  isActive
                    ? 'text-sidebar-primary'
                    : 'text-sidebar-foreground/50 group-hover:text-sidebar-foreground/80'
                )}
              />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-sidebar-border space-y-1 border-t px-2 py-3">
        <button
          type="button"
          onClick={onLogout}
          aria-label="登出"
          title={collapsed ? '登出' : undefined}
          className="text-sidebar-foreground/50 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors"
        >
          <LogOut className="size-4 shrink-0" aria-hidden="true" />
          {!collapsed && <span>登出</span>}
        </button>
        <button
          type="button"
          onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="text-sidebar-foreground/50 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors"
        >
          <ChevronLeft
            aria-hidden="true"
            className={cn(
              'size-4 shrink-0 transition-transform duration-200',
              collapsed && 'rotate-180'
            )}
          />
          <span className={collapsed ? 'sr-only' : ''}>{collapsed ? 'Expand' : 'Collapse'}</span>
        </button>
      </div>
    </aside>
  );
}
