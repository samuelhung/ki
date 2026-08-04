import { Pencil } from 'lucide-react';

interface TitleActionButtonProps {
  onOpen: () => void;
  disabled?: boolean;
}

export function TitleActionButton({ onOpen, disabled }: TitleActionButtonProps) {
  return (
    <button
      type="button"
      className="transcript-action-icon"
      title="修改标题"
      aria-label="修改标题"
      disabled={disabled}
      onClick={onOpen}
    >
      <Pencil size={14} />
    </button>
  );
}
