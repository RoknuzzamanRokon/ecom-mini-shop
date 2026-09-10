"use client";

import React from "react";
import Link from "next/link";

export default function Footer() {
  return (
    <footer className="w-full bg-surface border-t border-line py-6 mt-12 transition-colors duration-200">
      <div className="max-w-[1360px] mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-ink-muted">
        <div className="flex items-center gap-2">
          <span>© 2025 MiniShop. All rights reserved.</span>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-6">
          <Link href="#" className="hover:text-primary transition-colors">
            Privacy Policy
          </Link>
          <Link href="#" className="hover:text-primary transition-colors">
            Terms of Service
          </Link>
          <Link href="#" className="hover:text-primary transition-colors">
            Delivery Information
          </Link>
          <Link href="#" className="hover:text-primary transition-colors">
            Contact Support
          </Link>
        </div>
      </div>
    </footer>
  );
}
