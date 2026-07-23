import { lazy, Suspense } from "react";
import type { ReactNode } from "react";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { RequireAuthentication } from "../features/accounts/require-authentication";
import { AppLayout } from "../layouts/app-layout";
import { AccountSettingsPage } from "../pages/account-settings-page";
import { LoginPage } from "../pages/login-page";
import { RemindersPage } from "../pages/reminders-page";
import { SystemStatusPage } from "../pages/system-status-page";
import { TimeSettingsPage } from "../pages/time-settings-page";

const CalendarPage = lazy(() =>
  import("../pages/calendar-page").then((module) => ({ default: module.CalendarPage })),
);
const TasksPage = lazy(() =>
  import("../pages/tasks-page").then((module) => ({ default: module.TasksPage })),
);
const TodayPage = lazy(() =>
  import("../pages/today-page").then((module) => ({ default: module.TodayPage })),
);
const ChatPage = lazy(() =>
  import("../pages/chat-page").then((module) => ({ default: module.ChatPage })),
);
const ApprovalsPage = lazy(() =>
  import("../pages/approvals-page").then((module) => ({ default: module.ApprovalsPage })),
);
const BriefingsPage = lazy(() =>
  import("../pages/briefings-page").then((module) => ({ default: module.BriefingsPage })),
);
const NotificationSettingsPage = lazy(() =>
  import("../pages/notification-settings-page").then((module) => ({
    default: module.NotificationSettingsPage,
  })),
);

function lazyPage(page: ReactNode) {
  return <Suspense fallback={<p className="text-slate-400">正在加载页面…</p>}>{page}</Suspense>;
}

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuthentication />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: "/", element: <SystemStatusPage /> },
          { path: "/today", element: lazyPage(<TodayPage />) },
          { path: "/chat/:conversationId?", element: lazyPage(<ChatPage />) },
          { path: "/calendar", element: lazyPage(<CalendarPage />) },
          { path: "/tasks", element: lazyPage(<TasksPage />) },
          { path: "/reminders", element: <RemindersPage /> },
          { path: "/approvals", element: lazyPage(<ApprovalsPage />) },
          { path: "/briefings", element: lazyPage(<BriefingsPage />) },
          { path: "/settings/time", element: <TimeSettingsPage /> },
          { path: "/settings/account", element: <AccountSettingsPage /> },
          {
            path: "/settings/notifications",
            element: lazyPage(<NotificationSettingsPage />),
          },
        ],
      },
    ],
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
