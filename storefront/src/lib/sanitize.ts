import DOMPurify from "isomorphic-dompurify";

/**
 * Sanitize admin-authored HTML (e.g. Odoo product descriptions) before it is
 * passed to dangerouslySetInnerHTML. Strips scripts, event handlers, iframes,
 * javascript: URLs, etc. Defence-in-depth alongside the CSP.
 */
export function safeHtml(dirty: string | undefined | null): string {
  if (!dirty) return "";
  return DOMPurify.sanitize(dirty, {
    ALLOWED_TAGS: [
      "p", "br", "b", "strong", "i", "em", "u", "ul", "ol", "li",
      "h1", "h2", "h3", "h4", "span", "a", "blockquote",
    ],
    ALLOWED_ATTR: ["href", "target", "rel"],
    ALLOW_DATA_ATTR: false,
    FORBID_TAGS: ["style", "script", "iframe", "form", "img"],
  });
}
