import { type DragEvent, useId, useState } from "react";
import { ApiError, extractText } from "../lib/api";

// Mirrors settings.max_upload_bytes / SUPPORTED_TYPES for a fast client-side check --
// the server remains authoritative (enhancements/06). Same pattern as ResumeForm's
// own MIN_LENGTH mirroring settings.min_resume_chars.
const MAX_UPLOAD_BYTES = 5_000_000;
const ACCEPTED_EXTENSIONS = [".pdf", ".docx"];
const ACCEPT_ATTR =
  ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export interface ExtractedFileInfo {
  filename: string;
  charCount: number;
  truncated: boolean;
}

interface ResumeDropzoneProps {
  onExtracted: (text: string, info: ExtractedFileInfo) => void;
}

export function ResumeDropzone({ onExtracted }: ResumeDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [lastFile, setLastFile] = useState<ExtractedFileInfo | null>(null);
  const inputId = useId();

  function validateFile(file: File): string | null {
    const hasAcceptedExtension = ACCEPTED_EXTENSIONS.some((ext) => file.name.toLowerCase().endsWith(ext));
    if (!hasAcceptedExtension) return "Upload a PDF or DOCX resume.";
    if (file.size > MAX_UPLOAD_BYTES) return `File is too large (max ${MAX_UPLOAD_BYTES / 1_000_000} MB).`;
    return null;
  }

  async function handleFile(file: File) {
    setErrorMessage("");
    const validationError = validateFile(file);
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    setIsExtracting(true);
    try {
      const result = await extractText(file);
      const info: ExtractedFileInfo = {
        filename: result.filename,
        charCount: result.char_count,
        truncated: result.truncated,
      };
      onExtracted(result.text, info);
      setLastFile(info);
    } catch (error) {
      // Inline, next to the dropzone -- not a full-page ErrorState. Reuses the same
      // ApiError/detail-message path as every other request in the app.
      setErrorMessage(error instanceof ApiError ? error.message : "Couldn't extract text from that file.");
    } finally {
      setIsExtracting(false);
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) void handleFile(file);
  }

  return (
    <div className="space-y-2">
      <div
        role="group"
        aria-label="Drop, paste, or browse for a resume file"
        tabIndex={0}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onPaste={(event) => {
          const file = event.clipboardData.files[0];
          if (file) {
            event.preventDefault();
            void handleFile(file);
          }
        }}
        className={`flex flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed px-4 py-5 text-center transition focus:outline-none focus:ring-2 focus:ring-indigo-500/30 ${
          isDragging
            ? "border-indigo-400 bg-indigo-50 dark:border-indigo-500 dark:bg-indigo-950/30"
            : "border-slate-200 dark:border-slate-800"
        }`}
      >
        <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6 text-slate-400 dark:text-slate-600">
          <path
            d="M12 16V4m0 0 4 4m-4-4-4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {isExtracting ? (
            "Extracting text…"
          ) : (
            <>
              Drop a PDF or DOCX, paste one, or{" "}
              <label
                htmlFor={inputId}
                className="cursor-pointer font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
              >
                browse
              </label>
            </>
          )}
        </p>
        <input
          id={inputId}
          type="file"
          accept={ACCEPT_ATTR}
          className="sr-only"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleFile(file);
            event.target.value = "";
          }}
        />
      </div>

      {errorMessage && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300">
          {errorMessage}
        </p>
      )}

      {lastFile && !errorMessage && (
        <div className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:bg-slate-800/50 dark:text-slate-300">
          <span>
            Loaded <span className="font-medium">{lastFile.filename}</span> (
            {lastFile.charCount.toLocaleString()} characters{lastFile.truncated ? ", truncated" : ""})
          </span>
          <button
            type="button"
            onClick={() => setLastFile(null)}
            aria-label="Dismiss"
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}
