import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@simple-module-py/ui/components/ui/dialog';
import { Check, Copy } from 'lucide-react';
import { useState } from 'react';

interface Props {
  /** The plaintext token; the dialog is open while it is set. */
  token: string | null;
  onClose: () => void;
}

/** Shows a new token's secret — the only time anything ever will. */
export function CreatedTokenDialog({ token, onClose }: Props) {
  const { t } = useT();
  const [copied, setCopied] = useState(false);

  async function copy() {
    if (!token) return;
    try {
      await navigator.clipboard.writeText(token);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  function close() {
    setCopied(false);
    onClose();
  }

  return (
    <Dialog open={token !== null} onOpenChange={(open) => !open && close()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t(keys.api_tokens.created.title)}</DialogTitle>
          <DialogDescription>{t(keys.api_tokens.created.warning)}</DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-2">
          <code className="min-w-0 flex-1 break-all rounded-md border bg-muted px-3 py-2 font-mono text-xs">
            {token}
          </code>
          <Button type="button" variant="outline" size="sm" onClick={copy}>
            {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
            {copied ? t(keys.api_tokens.created.copied) : t(keys.api_tokens.created.copy)}
          </Button>
        </div>
        <DialogFooter>
          <Button type="button" onClick={close}>
            {t(keys.api_tokens.created.done)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
