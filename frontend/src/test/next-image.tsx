import type { ImgHTMLAttributes } from "react";

/** next/image props an <img> does not take. */
const IMAGE_ONLY_PROPS = ["fill", "sizes", "priority", "quality", "placeholder", "blurDataURL", "unoptimized", "loader"];

/**
 * next/image as a plain <img>, for component tests:
 *
 *   vi.mock("next/image", () => import("@/test/next-image"));
 */
export default function Image(props: ImgHTMLAttributes<HTMLImageElement> & Record<string, unknown>) {
  const imgProps: Record<string, unknown> = { ...props };
  IMAGE_ONLY_PROPS.forEach((name) => delete imgProps[name]);
  // eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text
  return <img {...(imgProps as ImgHTMLAttributes<HTMLImageElement>)} />;
}
