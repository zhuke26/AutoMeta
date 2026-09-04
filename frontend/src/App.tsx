import { Navigate, Route, Routes } from "react-router-dom";


function LibraryPlaceholder() {
  return (
    <main>
      <p>AutoMeta</p>
      <h1>Library</h1>
    </main>
  );
}


function NewReviewPlaceholder() {
  return (
    <main>
      <p>AutoMeta</p>
      <h1>New review</h1>
    </main>
  );
}


function ReviewPlaceholder() {
  return (
    <main>
      <p>AutoMeta</p>
      <h1>Review workspace</h1>
    </main>
  );
}


export function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/library" replace />} />
      <Route path="/library" element={<LibraryPlaceholder />} />
      <Route path="/reviews/new" element={<NewReviewPlaceholder />} />
      <Route path="/reviews/:reviewId/*" element={<ReviewPlaceholder />} />
    </Routes>
  );
}
