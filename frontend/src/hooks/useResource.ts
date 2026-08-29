import { useEffect, useState } from "react";

import { api } from "../api";

export type LoadState<T> = { data: T | null; loading: boolean; error: string | null };

export function useResource<T>(path: string): LoadState<T> & { reload: () => void } {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<LoadState<T>>({
    data: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    let active = true;
    setState((current) => ({ ...current, loading: true, error: null }));
    api<T>(path)
      .then((data) => active && setState({ data, loading: false, error: null }))
      .catch((error: unknown) => {
        if (active) {
          setState({
            data: null,
            loading: false,
            error: error instanceof Error ? error.message : "Unable to load data",
          });
        }
      });
    return () => {
      active = false;
    };
  }, [path, revision]);

  return { ...state, reload: () => setRevision((value) => value + 1) };
}
