import { useQuery } from "@tanstack/react-query";

import { apiRequest } from "./client";
import type { SystemStatus } from "./types";


export const systemStatusKey = ["system", "status"] as const;


export function getSystemStatus(): Promise<SystemStatus> {
  return apiRequest<SystemStatus>("/system/status");
}


export function useSystemStatus() {
  return useQuery({ queryKey: systemStatusKey, queryFn: getSystemStatus });
}
