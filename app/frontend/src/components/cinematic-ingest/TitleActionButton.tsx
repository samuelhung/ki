import { Pencil } from 'lucide-react';

interface TitleActionButtonProps {
  onOpen: () => void;
}

export function TitleActionButton({ onOpen }: TitleActionButtonProps) {
  return (
    <button
      type="button"
      className="transcript-action-icon"
      title="修改标题"
      aria-label="修改标题"
      onClick={onOpen}
    >
      <Pencil size={14} />
    </button>
  );
}
