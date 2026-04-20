import { Component, type ReactNode, type ErrorInfo } from "react";
import { AlertTriangle } from "lucide-react";

interface State {
  error: Error | null;
  stack: string;
}

/**
 * Catch runtime errors in a subtree. Without this, an exception during
 * render blanks out the page — the user sees a black screen and has no
 * way to diagnose. With this, they see a red panel + the stack trace.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null, stack: "" };

  static getDerivedStateFromError(error: Error): State {
    return { error, stack: error.stack ?? "" };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[ErrorBoundary]", error, info);
    this.setState({ stack: (error.stack ?? "") + "\n\nComponent stack:\n" + (info.componentStack ?? "") });
  }

  reset = () => this.setState({ error: null, stack: "" });

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 space-y-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            <h2 className="text-lg font-semibold text-foreground">
              Something went wrong rendering this page
            </h2>
          </div>
          <p className="text-sm text-muted-foreground">
            <span className="font-mono text-foreground">{this.state.error.message}</span>
          </p>
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer select-none hover:text-foreground">
              Stack trace
            </summary>
            <pre className="mt-2 max-h-[400px] overflow-auto rounded bg-background/60 p-3 border border-border font-mono whitespace-pre-wrap break-all">
              {this.state.stack || "(no stack available)"}
            </pre>
          </details>
          <div className="flex gap-2">
            <button
              onClick={this.reset}
              className="px-3 py-1 text-xs rounded border border-border hover:bg-accent/60"
            >
              Try again
            </button>
            <button
              onClick={() => (window.location.href = "/dashboard")}
              className="px-3 py-1 text-xs rounded border border-border hover:bg-accent/60"
            >
              Back to dashboard
            </button>
          </div>
          <p className="text-xs text-muted-foreground">
            Also check your browser DevTools console (Cmd+Opt+I → Console) for the full error.
          </p>
        </div>
      </div>
    );
  }
}
