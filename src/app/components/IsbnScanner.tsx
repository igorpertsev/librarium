import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { isIsbn13 } from '../utils/isbn';

/** The browser's own barcode reader (Chrome, Edge, Android); not in TypeScript's DOM types. */
interface DetectedBarcode {
  rawValue: string;
}
interface NativeBarcodeDetector {
  detect(source: HTMLVideoElement): Promise<DetectedBarcode[]>;
}
interface NativeBarcodeDetectorClass {
  new (options: { formats: string[] }): NativeBarcodeDetector;
  getSupportedFormats(): Promise<string[]>;
}

const SCAN_EVERY_MS = 250;
const SAME_CODE_PAUSE_MS = 2500;

type ScanError = 'denied' | 'noCamera' | 'failed';

/**
 * Scans ISBN barcodes with the camera. With `continuous` it keeps scanning and reports every
 * new code (stocktaking); otherwise it reports the first one and closes. An ISBN can also be
 * typed in, for books without a barcode or devices without a camera.
 */
export function IsbnScanner({
  open,
  onClose,
  onDetected,
  continuous = false,
}: {
  open: boolean;
  onClose: () => void;
  onDetected: (isbn: string) => void;
  continuous?: boolean;
}) {
  const { t } = useTranslation();
  // The dialog mounts its content a moment after opening: start once the element exists.
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [mounted, setMounted] = useState(false);
  const attachVideo = useCallback((element: HTMLVideoElement | null) => {
    videoRef.current = element;
    setMounted(element !== null);
  }, []);
  const [error, setError] = useState<ScanError | null>(null);
  const [typed, setTyped] = useState('');
  const [last, setLast] = useState<string | null>(null);
  // The latest callback, without restarting the camera when the parent re-renders.
  const detectedRef = useRef(onDetected);
  const closeRef = useRef(onClose);
  useEffect(() => {
    detectedRef.current = onDetected;
    closeRef.current = onClose;
  });

  useEffect(() => {
    const video = videoRef.current;
    if (!open || !mounted || !video) return;
    let stopped = false;
    let stream: MediaStream | null = null;
    let timer: number | undefined;
    let stopZxing: (() => void) | undefined;
    let recent: { code: string; at: number } | null = null;
    setError(null);
    setLast(null);

    const found = (raw: string) => {
      const code = raw.replace(/\D/g, '');
      if (stopped || !isIsbn13(code)) return;
      const now = Date.now();
      if (recent && recent.code === code && now - recent.at < SAME_CODE_PAUSE_MS) return;
      recent = { code, at: now };
      setLast(code);
      detectedRef.current(code);
      if (!continuous) closeRef.current();
    };

    const start = async () => {
      const constraints: MediaStreamConstraints = { video: { facingMode: { ideal: 'environment' } }, audio: false };
      const Native = (window as unknown as { BarcodeDetector?: NativeBarcodeDetectorClass }).BarcodeDetector;
      try {
        if (Native && (await Native.getSupportedFormats()).includes('ean_13')) {
          const detector = new Native({ formats: ['ean_13'] });
          stream = await navigator.mediaDevices.getUserMedia(constraints);
          if (stopped) return;
          video.srcObject = stream;
          await video.play();
          timer = window.setInterval(() => {
            if (video.readyState >= 2) {
              detector.detect(video).then((codes) => codes.forEach((c) => found(c.rawValue)), () => undefined);
            }
          }, SCAN_EVERY_MS);
        } else {
          // Other browsers: ZXing, loaded only when someone scans.
          const { BrowserMultiFormatOneDReader } = await import('@zxing/browser');
          const reader = new BrowserMultiFormatOneDReader();
          const controls = await reader.decodeFromConstraints(constraints, video, (result) => {
            if (result) found(result.getText());
          });
          if (stopped) controls.stop();
          else stopZxing = () => controls.stop();
        }
      } catch (e) {
        const name = e instanceof DOMException ? e.name : '';
        setError(name === 'NotAllowedError' ? 'denied' : name === 'NotFoundError' ? 'noCamera' : 'failed');
      }
    };
    void start();

    return () => {
      stopped = true;
      window.clearInterval(timer);
      stopZxing?.();
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [open, continuous, mounted]);

  const submitTyped = () => {
    const code = typed.replace(/[\s-]/g, '');
    if (!isIsbn13(code) && !/^\d{9}[\dXx]$/.test(code)) return;
    setTyped('');
    setLast(code);
    detectedRef.current(code);
    if (!continuous) onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('scanner.title')}</DialogTitle>
          <DialogDescription>{t(continuous ? 'scanner.hintContinuous' : 'scanner.hint')}</DialogDescription>
        </DialogHeader>
        <div className="relative overflow-hidden rounded-md bg-black aspect-video">
          <video ref={attachVideo} className="h-full w-full object-cover" muted playsInline aria-hidden="true" />
          <div className="pointer-events-none absolute inset-x-8 top-1/2 h-0.5 -translate-y-1/2 bg-red-500/80" />
        </div>
        {error && (
          <p role="alert" className="text-sm text-destructive dark:text-red-400">
            {t(`scanner.${error}`)}
          </p>
        )}
        {last && (
          <p role="status" className="text-sm">
            {t('scanner.found', { isbn: last })}
          </p>
        )}
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submitTyped();
          }}
        >
          <div className="flex-1 space-y-1">
            <Label htmlFor="typed-isbn">{t('scanner.type')}</Label>
            <Input id="typed-isbn" inputMode="numeric" value={typed} onChange={(e) => setTyped(e.target.value)} />
          </div>
          <Button type="submit" variant="outline" disabled={!typed.trim()}>
            {t('scanner.use')}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
