import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "@/context/ThemeContext";
import { AuthProvider } from "@/context/AuthContext";
import { ProfileProvider } from "@/context/ProfileContext";
import { FavoritesProvider } from "@/context/FavoritesContext";
import { CartProvider } from "@/context/CartContext";
import { LocationProvider } from "@/context/LocationContext";
import CartDrawer from "@/components/cart/CartDrawer";
import ThemeSwitcher from "@/components/theme/ThemeSwitcher";

const MATERIAL_SYMBOLS_CSS =
  '@import url("https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200") layer(base);';

export const metadata: Metadata = {
  title: "MiniShop — Storefront",
  description: "Modern e-commerce storefront with customizable color grading",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Google's icon stylesheet sets font-size: 24px and display on every
            icon. Loaded as a plain <link> it is unlayered and beats Tailwind's
            layered utilities, so text-[Npx] and hidden did nothing (BUG-095).
            Imported into the base layer, the utilities win. */}
        <style dangerouslySetInnerHTML={{ __html: MATERIAL_SYMBOLS_CSS }} />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
        {/* Anti-flash script */}
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var t = localStorage.getItem('minishop-theme') || 'ai';
                  var d = localStorage.getItem('minishop-dark') === '1';
                  document.documentElement.setAttribute('data-theme', t);
                  if (d) { document.documentElement.classList.add('dark'); }
                } catch (e) {
                  document.documentElement.setAttribute('data-theme', 'ai');
                }
              })();
            `,
          }}
        />
      </head>
      <body className="min-h-screen flex flex-col antialiased" suppressHydrationWarning>
        <ThemeProvider>
          <AuthProvider>
            <ProfileProvider>
              <FavoritesProvider>
                <CartProvider>
                  <LocationProvider>
                    {children}
                    <CartDrawer />
                    <ThemeSwitcher />
                  </LocationProvider>
                </CartProvider>
              </FavoritesProvider>
            </ProfileProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
