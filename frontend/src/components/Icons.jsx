const base = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true };

export const MicIcon = (props) => (
  <svg {...base} {...props}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
);

export const StopIcon = (props) => (
  <svg {...base} {...props}>
    <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
  </svg>
);

export const PlayIcon = (props) => (
  <svg {...base} {...props}>
    <path d="M7 5l12 7-12 7z" fill="currentColor" />
  </svg>
);

export const ReplayIcon = (props) => (
  <svg {...base} {...props}>
    <path d="M3 12a9 9 0 1 0 3-6.7M3 4v5h5" />
  </svg>
);

export const UploadIcon = (props) => (
  <svg {...base} {...props}>
    <path d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
  </svg>
);

export const FileIcon = (props) => (
  <svg {...base} {...props}>
    <path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7z" />
    <path d="M14 3v4h4" />
  </svg>
);

export const ArrowIcon = (props) => (
  <svg {...base} {...props}>
    <path d="M5 12h14m-5-5l5 5-5 5" />
  </svg>
);

export const AlertIcon = (props) => (
  <svg {...base} {...props}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 8v5m0 3h.01" />
  </svg>
);

export const CheckIcon = (props) => (
  <svg {...base} {...props}>
    <path d="M5 12l5 5 9-10" />
  </svg>
);

export const Logo = ({ size = 28 }) => (
  <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
    <rect x="3" y="12" width="4" height="8" rx="2" fill="currentColor" />
    <rect x="10" y="6" width="4" height="20" rx="2" fill="currentColor" />
    <rect x="17" y="9" width="4" height="14" rx="2" fill="currentColor" />
    <rect x="24" y="13" width="4" height="6" rx="2" fill="currentColor" />
  </svg>
);
