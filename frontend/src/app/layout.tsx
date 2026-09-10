import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "@/context/ThemeContext";
import { CartProvider } from "@/context/CartContext";
import CartDrawer from "@/components/cart/CartDrawer";
import ThemeSwitcher from "@/components/theme/ThemeSwitcher";

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
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200"
          rel="stylesheet"
        />
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
      <body className="min-h-screen flex flex-col antialiased">
        <ThemeProvider>
          <CartProvider>
            {children}
            <CartDrawer />
            <ThemeSwitcher />
          </CartProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
