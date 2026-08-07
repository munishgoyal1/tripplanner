import React from "react";
import ReactDOM from "react-dom/client";
import AnalyticsConsent from "./components/AnalyticsConsent";
import Root from "./publicEntry/Root";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
    <AnalyticsConsent />
  </React.StrictMode>
);
