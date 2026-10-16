# silver-barnacle

Vite + React + TypeScript + Tailwind CSS v4, with:

- [GSAP](https://github.com/greensock/GSAP) (`gsap`, `@gsap/react`) — animation
- [Lenis](https://github.com/darkroomengineering/lenis) (`lenis`) — smooth scrolling, synced to GSAP's ticker and ScrollTrigger in `src/hooks/useLenis.ts`
- [React Bits](https://github.com/DavidHDev/react-bits) — copy-in animated components via the shadcn CLI

## Develop

```bash
npm install
npm run dev
```

## Adding React Bits components

React Bits is registered in `components.json` as `@react-bits`. Add any component by name (TypeScript + Tailwind variant):

```bash
npx shadcn@latest add @react-bits/SplitText-TS-TW
```

Components land in `src/components/`. Browse them at https://reactbits.dev.
