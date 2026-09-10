# MiniShop AI Agent & Developer Guidelines

Refer to [GEMINI.md](./GEMINI.md) for full architectural and styling specifications.

### Key Commandments
1. **Currency**: Always use `৳` (Bangladeshi Taka). Never use `$`.
2. **Ports**: Django on `8001`, Next.js on `3000`.
3. **Design Tokens**: Use CSS variables (`bg-primary`, `bg-surface`, `text-ink`, `text-accent`), never hardcoded Tailwind palette colors.
4. **Sticky Navigation**: Keep Header and Navbar stuck together at `top: 0` on scroll.
5. **Mobile Layout**: Hide left sidebar on mobile (`hidden lg:flex`), provide category toggler on Navbar.
6. **Hero Banner**: Auto-playing category carousel on Home; single-category showcase when a category is selected.
7. **Product Detail**: Compact main image (`max-h-[430px]`), 5:7 column split, circular Amazon-style magnifying loupe.
8. **Verification**: Always run `python manage.py test shop` and `npm run build` before completing changes.
9. **Mandatory Git Commits**: For any modification or update stage, always run `git add` and `git commit -m "<subject line>"` with a clear descriptive message. Never leave completed changes uncommitted.

