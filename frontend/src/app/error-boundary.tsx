import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { hasError: boolean };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled frontend error", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <main className="grid min-h-screen place-items-center bg-slate-950 p-6 text-slate-100">
          <section className="max-w-md rounded-2xl border border-red-400/30 bg-slate-900 p-6">
            <h1 className="text-xl font-semibold">页面暂时无法显示</h1>
            <p className="mt-2 text-sm text-slate-300">请刷新页面重试；若问题持续，请联系维护者。</p>
          </section>
        </main>
      );
    }

    return this.props.children;
  }
}

