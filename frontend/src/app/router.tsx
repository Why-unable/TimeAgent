import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { AppLayout } from "../layouts/app-layout";
import { PlaceholderPage } from "../pages/placeholder-page";
import { RemindersPage } from "../pages/reminders-page";
import { SystemStatusPage } from "../pages/system-status-page";
import { TimeSettingsPage } from "../pages/time-settings-page";

const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <SystemStatusPage /> },
      { path: "/today", element: <PlaceholderPage title="Today" /> },
      { path: "/chat", element: <PlaceholderPage title="Chat" /> },
      { path: "/calendar", element: <PlaceholderPage title="Calendar" /> },
      { path: "/tasks", element: <PlaceholderPage title="Tasks" /> },
      { path: "/reminders", element: <RemindersPage /> },
      { path: "/settings/time", element: <TimeSettingsPage /> },
    ],
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
