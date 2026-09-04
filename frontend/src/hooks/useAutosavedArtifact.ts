import { useEffect, useRef, useState } from "react";

import { useSaveArtifact } from "../api/artifacts";
import type { ArtifactKind, ArtifactView } from "../api/types";


export type AutosaveState = "idle" | "saving" | "saved" | "error";


export function useAutosavedArtifact(
  reviewId: string,
  kind: ArtifactKind,
  payload: Record<string, unknown>,
  enabled: boolean,
) {
  const [state, setState] = useState<AutosaveState>("idle");
  const [artifact, setArtifact] = useState<ArtifactView>();
  const [error, setError] = useState<Error>();
  const payloadRef = useRef(payload);
  payloadRef.current = payload;
  const serialized = JSON.stringify(payload);
  const saveArtifact = useSaveArtifact();

  useEffect(() => {
    if (!enabled) {
      setState("idle");
      return;
    }
    const timer = window.setTimeout(() => {
      setState("saving");
      setError(undefined);
      saveArtifact.mutate(
        { reviewId, kind, payload: payloadRef.current },
        {
          onSuccess: (saved) => {
            setArtifact(saved);
            setState("saved");
          },
          onError: (failure) => {
            setError(failure);
            setState("error");
          },
        },
      );
    }, 600);
    return () => window.clearTimeout(timer);
  }, [enabled, kind, reviewId, saveArtifact.mutate, serialized]);

  return { artifact, error, state };
}
