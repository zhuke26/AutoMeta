import { Navigate, Route, Routes } from "react-router-dom";

import { LibraryPage } from "./pages/LibraryPage";
import { MetaAnalysisPage } from "./pages/MetaAnalysisPage";
import { NewReviewPage } from "./pages/NewReviewPage";
import { ProvenancePage } from "./pages/ProvenancePage";
import { ExtractionPage } from "./pages/ExtractionPage";
import { ReviewSetupPage } from "./pages/ReviewSetupPage";
import { ReviewEntryRedirect, ReviewWorkspace } from "./pages/ReviewWorkspace";
import { SearchPage } from "./pages/SearchPage";
import { ScreeningPage } from "./pages/ScreeningPage";
import { SystemStatusPage } from "./pages/SystemStatusPage";


export function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/library" replace />} />
      <Route path="/library" element={<LibraryPage />} />
      <Route path="/reviews/new" element={<NewReviewPage />} />
      <Route path="/system" element={<SystemStatusPage />} />
      <Route path="/reviews/:reviewId" element={<ReviewWorkspace />}>
        <Route index element={<ReviewEntryRedirect />} />
        <Route path="setup" element={<ReviewSetupPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="screening" element={<ScreeningPage />} />
        <Route path="extraction" element={<ExtractionPage />} />
        <Route path="meta-analysis" element={<MetaAnalysisPage />} />
        <Route path="provenance" element={<ProvenancePage />} />
        <Route path="*" element={<ReviewEntryRedirect />} />
      </Route>
    </Routes>
  );
}
