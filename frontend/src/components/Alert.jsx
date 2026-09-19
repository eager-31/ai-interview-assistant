import { AlertIcon, CheckIcon } from "./Icons";

/** `actions` is a list of { label, onClick }. Errors are announced to screen readers immediately. */
export default function Alert({ kind = "error", title, children, actions = [] }) {
  const Icon = kind === "success" ? CheckIcon : AlertIcon;
  return (
    <div className={`alert alert-${kind}`} role={kind === "error" ? "alert" : "status"}>
      <Icon className="alert-icon" />
      <div className="alert-body">
        {title && <p className="alert-title">{title}</p>}
        {children && <p>{children}</p>}
        {actions.length > 0 && (
          <div className="row alert-actions">
            {actions.map((action) => (
              <button key={action.label} type="button" className="btn btn-secondary btn-sm" onClick={action.onClick}>
                {action.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
