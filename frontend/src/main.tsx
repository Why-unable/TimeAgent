import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { AppProviders } from "./app/providers";
import { AppRouter } from "./app/router";
import { bootstrap } from "./bootstrap";
import { registerServiceWorker } from "./pwa";
import "@fullcalendar/react/skeleton.css";
import "@fullcalendar/react/themes/monarch/theme.css";
import "@fullcalendar/react/themes/monarch/palettes/blue.css";
import "./styles/index.css";

function render() {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <AppProviders>
        <AppRouter />
      </AppProviders>
    </StrictMode>,
  );
}

// Hydrate auth (and native platform setup) before the first render so the
// initial current-user request carries the token. Render regardless of outcome.
void bootstrap().finally(render);

void registerServiceWorker();
