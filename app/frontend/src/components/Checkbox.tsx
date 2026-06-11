import React from 'react';

interface CheckboxProps {
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
}

export default function Checkbox({ checked, onChange, disabled }: CheckboxProps) {
  return (
    <button
      onClick={disabled ? undefined : onChange}
      disabled={disabled}
      className={`w-4 h-4 rounded border transition-colors shrink-0 flex items-center justify-center cursor-pointer ${
        disabled ? 'opacity-40 cursor-not-allowed' : ''
      } ${
        checked
          ? 'bg-purple-500 border-purple-500'
          : 'bg-[#141518] border-[#2A2B30] hover:border-purple-500/50'
      }`}
    >
      {checked && (
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <path d="M2 5L4 7L8 3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      )}
    </button>
  );
}
