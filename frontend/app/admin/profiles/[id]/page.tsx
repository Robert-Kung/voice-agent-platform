'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { profilesApi } from '@/lib/admin-api';
import type { Profile } from '@/lib/admin-api';

export default function ProfileDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editDisplayName, setEditDisplayName] = useState('');
  const [editConfig, setEditConfig] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (id === 'new') {
      setProfile({
        id: 'new',
        name: '',
        display_name: '',
        description: '',
        is_active: true,
        config: { instructions: '', tools: [] },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
      setEditDisplayName('');
      setEditConfig(JSON.stringify({ instructions: '', tools: [] }, null, 2));
      setLoading(false);
      return;
    }

    profilesApi
      .get(id)
      .then((p) => {
        setProfile(p);
        setEditDisplayName(p.display_name);
        setEditConfig(JSON.stringify(p.config, null, 2));
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const handleSave = async () => {
    if (!profile) return;
    setSaving(true);
    setMessage(null);
    try {
      const configObj = JSON.parse(editConfig);
      if (id === 'new') {
        const name = prompt('Enter unique profile name (lowercase, no spaces):');
        if (!name) {
          setSaving(false);
          return;
        }
        const created = await profilesApi.create({
          name,
          display_name: editDisplayName,
          config: configObj,
        });
        router.push(`/admin/profiles/${created.id}`);
      } else {
        const updated = await profilesApi.update(id, {
          display_name: editDisplayName,
          config: configObj,
        });
        setProfile(updated);
        setMessage('Saved.');
        setTimeout(() => setMessage(null), 2000);
      }
    } catch (e) {
      setMessage(`Error: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div>Loading...</div>;
  if (error) return <div className="text-red-500">Error: {error}</div>;
  if (!profile) return <div>Profile not found.</div>;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/admin/profiles" className="text-primary text-sm hover:underline">
          ← Back to profiles
        </Link>
      </div>

      <div>
        <h2 className="text-2xl font-bold">{id === 'new' ? 'New Profile' : profile.name}</h2>
        {id !== 'new' && <p className="text-foreground/60 font-mono text-xs">{profile.id}</p>}
      </div>

      <div className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium">Display Name</label>
          <input
            type="text"
            value={editDisplayName}
            onChange={(e) => setEditDisplayName(e.target.value)}
            className="border-border w-full rounded-md border bg-transparent px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium">Config (JSON)</label>
          <textarea
            value={editConfig}
            onChange={(e) => setEditConfig(e.target.value)}
            rows={25}
            className="border-border w-full rounded-md border bg-transparent px-3 py-2 font-mono text-xs"
            spellCheck={false}
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="bg-primary text-primary-foreground rounded px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
          {message && (
            <span
              className={`text-sm ${message.startsWith('Error') ? 'text-red-500' : 'text-green-500'}`}
            >
              {message}
            </span>
          )}
        </div>

        {id !== 'new' && (
          <div className="text-foreground/60 text-xs">
            Try this profile:{' '}
            <Link href={`/?profile=${profile.name}`} className="text-primary hover:underline">
              /?profile={profile.name}
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
