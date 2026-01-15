import React from "react";
import {
  Link,
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
  useRouterState,
} from "@tanstack/react-router";
import { AdminProjectsPage } from "@/views/admin/AdminProjectsPage";
import { AdminProjectPage } from "@/views/admin/AdminProjectPage";
import { SharePage } from "@/views/share/SharePage";
import { SamplePage } from "@/views/SamplePage";

const rootRoute = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  const { location } = useRouterState();
  const logoTarget = React.useMemo(() => {
    const path = location.pathname;
    if (path.startsWith("/share/")) return path;
    return "/projects";
  }, [location.pathname]);

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[var(--bg-primary)] border-b border-[var(--border-default)]">
        <div className="mx-auto flex max-w-7xl items-center px-5 py-4">
          <Link to={logoTarget} aria-label="Results landing">
            <img
              src="https://cdn.prod.website-files.com/64cfa0ffd93ac106369335fa/64cfa57b8416a474a5c3d68f_Qvantify.svg"
              alt="Qvantify"
              className="h-6 w-auto brand-logo"
            />
          </Link>
        </div>
      </header>

      {/* Main content */}
      <main className="animate-fade-in">
        <Outlet />
      </main>
    </div>
  );
}

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: async () => {
    throw redirect({ to: "/projects" });
  },
});

const projectsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects",
  component: AdminProjectsPage,
});

const projectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects/$projectId",
  component: AdminProjectPage,
});

const shareRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/share/$token",
  component: SharePage,
});

const sampleRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sample",
  component: SamplePage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  projectsRoute,
  projectRoute,
  shareRoute,
  sampleRoute,
]);

export const router = createRouter({
  routeTree,
  defaultPreload: "intent",
  basepath: "/results",
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
