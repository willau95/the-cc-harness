/**
 * Thin re-export of react-router-dom so components can import from a stable local path.
 * Paperclip has a company-prefix-injecting Link here; we don't need that.
 */
export * from "react-router-dom";
export { Link, NavLink, Navigate, useNavigate } from "react-router-dom";
