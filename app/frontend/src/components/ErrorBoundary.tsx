import React, { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="text-[40px] mb-3">⚠️</div>
          <div className="text-base font-medium text-white mb-1">页面出错了</div>
          <div className="text-sm text-gray-500 mb-3">
            {this.state.error?.message || '未知错误'}
          </div>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-[#2A2B30] text-white hover:bg-[#3A3B40] transition-colors"
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
