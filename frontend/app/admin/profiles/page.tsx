'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { profilesApi } from '@/lib/admin-api';
import type { Profile } from '@/lib/admin-api';

export default function ProfilesPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showInactive, setShowInactive] = useState(false);

  const load = () => {
    setLoading(true);
    profilesApi
      .list(!showInactive)
      .then(setProfiles)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showInactive]);

  const handleDeactivate = async (id: string, name: string) => {
    if (!confirm(`Deactivate profile "${name}"?`)) return;
    try {
      await profilesApi.deactivate(id);
      load();
    } catch (e) {
      alert(`Failed: ${(e as Error).message}`);
    }
  };

  if (loading) return <div>Loading...</div>;
  if (error) return <div className="text-red-500">Error: {error}</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Profiles</h2>
          <p className="text-foreground/60 text-sm">Agent configuration profiles</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
            />
            Show inactive
          </label>
          <Link
            href="/admin/profiles/new"
            className="bg-primary text-primary-foreground rounded px-3 py-1.5 text-sm font-medium"
          >
            + New Profile
          </Link>
        </div>
      </div>

      {profiles.length === 0 ? (
        <div className="text-foreground/60">No profiles found.</div>
      ) : (
        <div className="border-border rounded-md border">
          <table className="w-full text-sm">
            <thead className="border-border text-foreground/60 border-b">
              <tr>
                <th className="p-3 text-left font-medium">Name</th>
                <th className="p-3 text-left font-medium">Display Name</th>
                <th className="p-3 text-left font-medium">Tools</th>
                <th className="p-3 text-left font-medium">Status</th>
                <th className="p-3 text-left font-medium">Updated</th>
                <th className="p-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((p) => {
                const tools = (p.config.tools as Array<{ name: string }> | undefined) || [];
                return (
                  <tr key={p.id} className="border-border border-b last:border-0">
                    <td className="p-3 font-mono text-xs">
                      <Link
                        href={`/admin/profiles/${p.id}`}
                        className="text-primary hover:underline"
                      >
                        {p.name}
                      </Link>
                    </td>
                    <td className="p-3">{p.display_name}</td>
                    <td className="text-foreground/70 p-3">
                      {tools.length ? tools.map((t) => t.name).join(', ') : '(none)'}
                    </td>
                    <td className="p-3">
                      <span
                        className={`rounded px-2 py-0.5 text-xs ${
                          p.is_active
                            ? 'bg-green-500/20 text-green-700 dark:text-green-400'
                            : 'bg-gray-500/20 text-gray-600 dark:text-gray-400'
                        }`}
                      >
                        {p.is_active ? 'active' : 'inactive'}
                      </span>
                    </td>
                    <td className="text-foreground/70 p-3">
                      {new Date(p.updated_at).toLocaleString()}
                    </td>
                    <td className="p-3 text-right">
                      {p.is_active && (
                        <button
                          onClick={() => handleDeactivate(p.id, p.name)}
                          className="text-red-500 hover:underline"
                        >
                          Deactivate
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
