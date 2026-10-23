import Header, { type HeaderProps } from "@/components/layout/Header";
import Navbar, { type NavbarProps } from "@/components/layout/Navbar";

/**
 * The storefront's Header and Navbar, stuck together at the top on scroll
 * (project rule 4). Every storefront page, route boundary and loading branch
 * renders this one component, so no state shows the header alone or lets the
 * pair scroll away (BUG-099). Props go to whichever of the two takes them.
 */
export default function StorefrontChrome({ onSearch, searchQuery, ...navbar }: HeaderProps & NavbarProps) {
  return (
    <div className="sticky top-0 z-40 w-full shadow-sm">
      <Header onSearch={onSearch} searchQuery={searchQuery} />
      <Navbar {...navbar} />
    </div>
  );
}
