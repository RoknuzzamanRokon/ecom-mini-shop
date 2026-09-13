"use client";

import React, { useState } from "react";
import SellerGuard from "@/components/seller/SellerGuard";
import SellerSidebar from "@/components/seller/SellerSidebar";
import SellerHeader from "@/components/seller/SellerHeader";

export default function SellerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  return (
    <SellerGuard>
      <div className="min-h-screen bg-page flex flex-col text-ink transition-colors duration-200">
        <SellerSidebar
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
        />
        <div className="lg:pl-64 flex flex-col flex-1">
          <SellerHeader onMenuToggle={() => setIsSidebarOpen(!isSidebarOpen)} />
          <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-[1400px] w-full mx-auto">
            {children}
          </main>
        </div>
      </div>
    </SellerGuard>
  );
}
