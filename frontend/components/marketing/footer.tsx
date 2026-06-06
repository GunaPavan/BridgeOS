import Link from "next/link";
import { Github, Heart } from "lucide-react";

export function MarketingFooter() {
  return (
    <footer
      className="border-t border-white/5 bg-surface/30 px-6 py-12"
      data-testid="marketing-footer"
    >
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-10 md:grid-cols-4">
        <div>
          <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-xl font-bold text-transparent">
            Bridge OS
          </span>
          <p className="mt-2 text-xs text-white/50">
            The operating system for Blood Bridges. Built for the AI for Good
            Hackathon 2026.
          </p>
        </div>

        <div>
          <h4 className="text-xs uppercase tracking-widest text-white/40">
            Product
          </h4>
          <ul className="mt-3 space-y-2 text-sm text-white/70">
            <li><Link href="/bridges" className="hover:text-white">Bridges</Link></li>
            <li><Link href="/recommendations" className="hover:text-white">Recommendations</Link></li>
            <li><Link href="/simulator" className="hover:text-white">Simulator</Link></li>
            <li><Link href="/agent" className="hover:text-white">Care Agent</Link></li>
          </ul>
        </div>

        <div>
          <h4 className="text-xs uppercase tracking-widest text-white/40">
            Learn
          </h4>
          <ul className="mt-3 space-y-2 text-sm text-white/70">
            <li><Link href="/how-it-works" className="hover:text-white">How it works</Link></li>
            <li><Link href="/about" className="hover:text-white">About the team</Link></li>
            <li>
              <a
                href="https://bloodwarriors.in"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-white"
              >
                Blood Warriors Foundation
              </a>
            </li>
          </ul>
        </div>

        <div>
          <h4 className="text-xs uppercase tracking-widest text-white/40">
            Hackathon
          </h4>
          <ul className="mt-3 space-y-2 text-sm text-white/70">
            <li>AI for Good 2026</li>
            <li>Blend360</li>
            <li>Blood Warriors · HackCulture</li>
          </ul>
        </div>
      </div>

      <div className="mx-auto mt-10 flex max-w-7xl flex-col items-center justify-between gap-3 border-t border-white/5 pt-6 text-xs text-white/40 md:flex-row">
        <p>
          © 2026 AlgoWarriors · Gunaputra Nagendra Pavan Yedida · Aakash Jangeeti
        </p>
        <p className="inline-flex items-center gap-1.5">
          Built with <Heart className="h-3 w-3 text-primary" /> for thalassemia
          patients across India.
        </p>
      </div>
    </footer>
  );
}
