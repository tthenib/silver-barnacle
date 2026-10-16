import SplitText from '@/components/SplitText'
import { useLenis } from '@/hooks/useLenis'

function App() {
  useLenis()

  return (
    <main>
      <section className="flex min-h-svh items-center justify-center p-6">
        <SplitText
          text="GSAP + Lenis + React Bits"
          className="text-center text-4xl font-semibold md:text-6xl"
        />
      </section>
      <section className="flex min-h-svh items-center justify-center p-6">
        <SplitText
          text="Scroll-triggered, smooth-scrolled."
          className="text-center text-3xl md:text-5xl"
        />
      </section>
    </main>
  )
}

export default App
