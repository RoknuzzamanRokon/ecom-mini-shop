import type { AnchorHTMLAttributes, ReactNode } from "react";

/** Link-only props that must not reach the <a>. */
const LINK_ONLY_PROPS = ["prefetch", "replace", "scroll", "shallow", "passHref", "legacyBehavior"];

/**
 * next/link as a plain anchor, for component tests:
 *
 *   vi.mock("next/link", () => import("@/test/next-link"));
 */
export default function Link({
  href,
  children,
  ...rest
}: { href: string; children?: ReactNode } & AnchorHTMLAttributes<HTMLAnchorElement>) {
  const anchorProps: Record<string, unknown> = { ...rest };
  LINK_ONLY_PROPS.forEach((name) => delete anchorProps[name]);
  return (
    <a href={href} {...anchorProps}>
      {children}
    </a>
  );
}
