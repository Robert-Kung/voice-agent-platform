'use client';

import { useEffect, useState } from 'react';
import { modelDefaultsApi } from '@/lib/admin-api';
import { FALLBACK_MODEL_CATALOG, type ModelCatalog } from '@/lib/model-catalog';

export interface ModelCatalogState {
  catalog: ModelCatalog;
  loading: boolean;
  /** Set when the live fetch failed and the offline fallback is in use. The UI
   *  surfaces this rather than silently rendering an empty/stale picker (task 6.2). */
  error: string | null;
}

/**
 * Fetch the backend model-defaults catalog (single source of truth). While in
 * flight, `loading` is true and the offline fallback is served so pickers never
 * render empty; on failure `error` is set and the fallback stays in use.
 */
export function useModelCatalog(): ModelCatalogState {
  const [catalog, setCatalog] = useState<ModelCatalog>(FALLBACK_MODEL_CATALOG);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    modelDefaultsApi
      .get()
      .then((c) => {
        if (!cancelled) {
          setCatalog(c);
          setError(null);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { catalog, loading, error };
}
