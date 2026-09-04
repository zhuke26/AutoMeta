import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "./client";


export interface PdfDisclosureSetting {
  acknowledged: boolean;
}

export const pdfDisclosureKey = ["settings", "pdf-disclosure"] as const;


export function getPdfDisclosure(): Promise<PdfDisclosureSetting> {
  return apiRequest<PdfDisclosureSetting>("/settings/pdf-disclosure");
}


export function setPdfDisclosure(acknowledged: boolean): Promise<PdfDisclosureSetting> {
  return apiRequest<PdfDisclosureSetting>("/settings/pdf-disclosure", {
    method: "PUT",
    body: JSON.stringify({ acknowledged }),
  });
}


export function usePdfDisclosure() {
  return useQuery({ queryKey: pdfDisclosureKey, queryFn: getPdfDisclosure });
}


export function useSetPdfDisclosure() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: setPdfDisclosure,
    onSuccess: (setting) => queryClient.setQueryData(pdfDisclosureKey, setting),
  });
}
