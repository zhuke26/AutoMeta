import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { LibraryPage } from "./pages/LibraryPage";
import { NewReviewPage } from "./pages/NewReviewPage";


function ReviewPlaceholder() {
  return (
    <AppShell reviewLabel="Untitled review">
      <main>
        <h1>Review workspace</h1>
      </main>
    </AppShell>
  );
}


export function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/library" replace />} />
      <Route path="/library" element={<LibraryPage />} />
      <Route path="/reviews/new" element={<NewReviewPage />} />
      <Route path="/reviews/:reviewId/*" element={<ReviewPlaceholder />} />
    </Routes>
  );
}
