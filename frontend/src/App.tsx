import { Navigate, Route, Routes } from "react-router-dom";

import { LibraryPage } from "./pages/LibraryPage";
import { NewReviewPage } from "./pages/NewReviewPage";
import { ReviewSetupPage } from "./pages/ReviewSetupPage";
import { ReviewEntryRedirect, ReviewWorkspace } from "./pages/ReviewWorkspace";
import { StagePendingPage } from "./pages/StagePendingPage";


export function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/library" replace />} />
      <Route path="/library" element={<LibraryPage />} />
      <Route path="/reviews/new" element={<NewReviewPage />} />
      <Route path="/reviews/:reviewId" element={<ReviewWorkspace />}>
        <Route index element={<ReviewEntryRedirect />} />
        <Route path="setup" element={<ReviewSetupPage />} />
        <Route path="search" element={<StagePendingPage stage="search" />} />
        <Route path="screening" element={<StagePendingPage stage="screening" />} />
        <Route path="extraction" element={<StagePendingPage stage="extraction" />} />
        <Route path="meta-analysis" element={<StagePendingPage stage="meta_analysis" />} />
        <Route path="*" element={<ReviewEntryRedirect />} />
      </Route>
    </Routes>
  );
}
