import React from "react";

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, errorMessage: "" };
  }

  static getDerivedStateFromError(error) {
    return {
      hasError: true,
      errorMessage: error?.message || "Unexpected render error.",
    };
  }

  componentDidUpdate(prevProps) {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, errorMessage: "" });
    }
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <section className="render-error card-shell">
        <div className="render-error-copy">
          <span className="render-error-badge">Render error</span>
          <h2>Could not render this conversation.</h2>
          <p>{this.state.errorMessage}</p>
        </div>
      </section>
    );
  }
}
