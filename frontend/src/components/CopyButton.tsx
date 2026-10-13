import { useState } from "react";
import { Icon } from "./Icon";

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be refused (insecure context, permissions). The text is visible and selectable nearby.
      setCopied(false);
    }
  }

  return (
    <button type="button" className="icon-btn" onClick={copy} aria-label={copied ? "Copied" : label} title={label}>
      <Icon name={copied ? "check" : "copy"} size={14} />
    </button>
  );
}
