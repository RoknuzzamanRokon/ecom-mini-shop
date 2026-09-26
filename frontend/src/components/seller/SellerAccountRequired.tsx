"use client";

import Link from "next/link";

/**
 * Shown by SellerGuard to a signed-in account that has no seller profile.
 * Styles and animations live in globals.css under "Seller account required".
 */
export default function SellerAccountRequired({ account }: { account?: string }) {
  return (
    <div className="seller-required">
      <div className="seller-required__card">
        <div className="seller-required__stage">
          <svg
            className="seller-required__figure"
            viewBox="0 0 200 260"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
            focusable="false"
          >
            <ellipse className="seller-required__ground" cx="100" cy="248" rx="55" ry="9" />
            <rect className="seller-required__legs" x="78" y="175" width="18" height="55" rx="6" />
            <rect className="seller-required__legs" x="104" y="175" width="18" height="55" rx="6" />
            <rect className="seller-required__shoes" x="76" y="222" width="22" height="10" rx="3" />
            <rect className="seller-required__shoes" x="102" y="222" width="22" height="10" rx="3" />
            <path className="seller-required__suit" d="M65 120 Q100 108 135 120 L140 185 Q100 198 60 185 Z" />
            <path className="seller-required__shirt" d="M90 122 L100 140 L110 122 L104 118 L96 118 Z" />
            <path className="seller-required__tie" d="M97 122 L103 122 L107 150 L100 190 L93 150 Z" />
            <path className="seller-required__suit" d="M132 128 Q150 140 146 165 Q140 172 130 168 Q136 148 122 132 Z" />
            <g className="seller-required__arm">
              <path className="seller-required__suit" d="M68 128 Q48 118 42 96 Q46 88 55 90 Q58 108 76 122 Z" />
              <circle className="seller-required__skin" cx="45" cy="88" r="9" />
            </g>
            <g className="seller-required__head">
              <rect className="seller-required__skin" x="92" y="92" width="16" height="16" />
              <circle className="seller-required__skin" cx="100" cy="68" r="34" />
              <circle className="seller-required__skin" cx="66" cy="70" r="6" />
              <circle className="seller-required__skin" cx="134" cy="70" r="6" />
              <path className="seller-required__hair" d="M67 60 Q64 28 100 28 Q136 28 133 60 Q128 40 100 40 Q72 40 67 60Z" />
              <rect className="seller-required__hair" x="80" y="56" width="14" height="4" rx="2" />
              <rect className="seller-required__hair" x="106" y="56" width="14" height="4" rx="2" />
              <g className="seller-required__eye seller-required__eye--left">
                <circle className="seller-required__eye-white" cx="87" cy="66" r="5.5" />
                <circle className="seller-required__pupil" cx="87" cy="66" r="2.6" />
              </g>
              <g className="seller-required__eye seller-required__eye--right">
                <circle className="seller-required__eye-white" cx="113" cy="66" r="5.5" />
                <circle className="seller-required__pupil" cx="113" cy="66" r="2.6" />
              </g>
              <path className="seller-required__nose" d="M99 70 Q97 78 100 80 Q103 78 101 70Z" />
              <path className="seller-required__hair" d="M70 72 Q72 96 100 98 Q128 96 130 72 Q128 90 100 92 Q72 90 70 72Z" />
              <path className="seller-required__mouth" d="M90 84 Q100 82 110 84" />
            </g>
            <g>
              <circle className="seller-required__badge-ring" cx="150" cy="42" r="14" />
              <circle className="seller-required__badge" cx="150" cy="42" r="14" />
              <rect
                className="seller-required__badge-mark"
                x="143"
                y="39.5"
                width="14"
                height="5"
                rx="2.5"
                transform="rotate(45 150 42)"
              />
            </g>
          </svg>
        </div>

        <h1 className="seller-required__title">Seller Account Required</h1>
        <p className="seller-required__text">
          The account <b>{account}</b> is not currently registered as a seller on <b>MiniShop</b>.
          To open your shop and sell products, please apply through platform administration.
        </p>

        <div className="seller-required__actions">
          <Link href="/" className="seller-required__btn seller-required__btn--primary">
            Storefront
          </Link>
          <Link href="/profile" className="seller-required__btn seller-required__btn--secondary">
            Customer Profile
          </Link>
        </div>
      </div>
    </div>
  );
}
