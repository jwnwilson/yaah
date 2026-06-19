import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";
import { IconButton } from "@/components/ui/IconButton";

interface ChatComposerProps {
  value: string;
  onChange: (text: string) => void;
  onSubmit: (text: string) => void;
  placeholder: string;
  sending?: boolean;
  micSupported?: boolean;
  micListening?: boolean;
  onMicToggle?: () => void;
}

export function ChatComposer({
  value,
  onChange,
  onSubmit,
  placeholder,
  sending,
  micSupported,
  micListening,
  onMicToggle,
}: ChatComposerProps) {
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  };

  return (
    <form className="flex items-center gap-1 border-t border-line p-2" onSubmit={submit}>
      <Input placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} />
      {micSupported && (
        <IconButton
          label={micListening ? "Stop dictation" : "Dictate"}
          title="Voice input"
          aria-pressed={micListening}
          onClick={onMicToggle}
          className={micListening ? "animate-pulse text-danger" : undefined}
        >
          <span aria-hidden="true">🎤</span>
        </IconButton>
      )}
      <Button type="submit" size="sm" loading={sending}>
        Send
      </Button>
    </form>
  );
}
