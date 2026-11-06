import { ReactNode, useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from './ui/alert-dialog';
import { buttonVariants } from './ui/button';

export interface ConfirmOptions {
  title: string;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Red confirm button, for actions that delete or cancel something. */
  destructive?: boolean;
}

/**
 * Promise-based confirmation dialog:
 *
 *   const { confirm, confirmDialog } = useConfirm();
 *   if (await confirm({ title: 'Delete?', destructive: true })) remove();
 *   ...
 *   return <>{page}{confirmDialog}</>;
 */
export function useConfirm() {
  const { t } = useTranslation();
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<((confirmed: boolean) => void) | null>(null);

  const settle = useCallback((confirmed: boolean) => {
    resolver.current?.(confirmed);
    resolver.current = null;
    setOptions(null);
  }, []);

  const confirm = useCallback(
    (next: ConfirmOptions) =>
      new Promise<boolean>((resolve) => {
        resolver.current?.(false); // a newer request replaces an unanswered one
        resolver.current = resolve;
        setOptions(next);
      }),
    [],
  );

  const confirmDialog = (
    <AlertDialog open={options !== null} onOpenChange={(open) => !open && settle(false)}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{options?.title}</AlertDialogTitle>
          {options?.description && (
            <AlertDialogDescription>{options.description}</AlertDialogDescription>
          )}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => settle(false)}>
            {options?.cancelLabel ?? t('confirm.cancel')}
          </AlertDialogCancel>
          <AlertDialogAction
            className={options?.destructive ? buttonVariants({ variant: 'destructive' }) : undefined}
            onClick={() => settle(true)}
          >
            {options?.confirmLabel ?? t('confirm.confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  return { confirm, confirmDialog };
}
