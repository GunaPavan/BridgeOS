import Link from "next/link";
import {
  ArrowRight,
  Award,
  BrainCircuit,
  ExternalLink,
  Github,
  Heart,
  Linkedin,
  Sparkles,
  Target,
  Users,
} from "lucide-react";

import { MarketingFooter } from "@/components/marketing/footer";
import { MarketingNav } from "@/components/marketing/nav";

export const metadata = {
  title: "About — Bridge OS",
  description:
    "Bridge OS is built by AlgoWarriors — Gunaputra Nagendra Pavan Yedida and Aakash Jangeeti — for the AI for Good Hackathon 2026 in support of the Blood Warriors Foundation.",
};

const TEAM = [
  {
    name: "Gunaputra Nagendra Pavan Yedida",
    linkedin: "https://www.linkedin.com/in/gunapavan/",
    github: "https://github.com/GunaPavan",
  },
  {
    name: "Aakash Jangeeti",
    linkedin: "https://linkedin.com/in/aakash-jangeeti-a8015821b",
    github: "https://github.com/Webdesigner4everyone002",
  },
];

const VALUES = [
  {
    icon: Target,
    title: "Augment, don't replace",
    body:
      "Blood Warriors runs the Blood Bridge model brilliantly with humans and WhatsApp. We add intelligence to what already works — never propose a workflow nobody asked for.",
  },
  {
    icon: BrainCircuit,
    title: "Transparent ML",
    body:
      "Every model surfaces SHAP factors. Every recommendation explains its score. No black boxes for clinical-adjacent decisions.",
  },
  {
    icon: Heart,
    title: "Patients first",
    body:
      "The destabilising donor in our demo is named — Priya — to keep us honest. A churned cohort means a missed transfusion. We optimise for the patient's calendar, not the dashboard's.",
  },
];

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-background text-white">
      <MarketingNav />

      {/* ---- Hero ---- */}
      <section className="border-b border-white/5 px-6 py-20">
        <div className="mx-auto max-w-4xl">
          <p className="text-xs uppercase tracking-widest text-accent">About</p>
          <h1 className="mt-3 text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
            Two engineers, one Blood Warriors mission, one weekend hackathon.
          </h1>
          <p className="mt-5 text-lg leading-relaxed text-white/65">
            Bridge OS is built by <span className="text-white">AlgoWarriors</span> —
            a two-person team competing in the AI for Good Hackathon 2026
            (Blend360, with Blood Warriors Foundation and HackCulture as
            impact partners). Every line of code, model, and integration was
            written for this challenge.
          </p>
        </div>
      </section>

      {/* ---- Mission ---- */}
      <section className="border-b border-white/5 bg-surface/20 px-6 py-20">
        <div className="mx-auto max-w-5xl">
          <div className="grid grid-cols-1 gap-12 md:grid-cols-2">
            <div>
              <div className="flex items-center gap-3">
                <Heart className="h-5 w-5 text-primary" />
                <p className="text-xs uppercase tracking-widest text-primary/80">
                  Mission
                </p>
              </div>
              <h2 className="mt-3 text-3xl font-bold">
                Make every Blood Bridge survive 20 years.
              </h2>
              <p className="mt-5 text-base leading-relaxed text-white/65">
                Thalassemia major is a lifelong diagnosis. The patient needs a
                transfusion every 18 days — that's roughly 400 transfusions in a
                two-decade horizon. Blood Warriors' Blood Bridge model commits 8–10
                donors per patient so the same trusted faces show up, year after year.
              </p>
              <p className="mt-4 text-base leading-relaxed text-white/65">
                Bridge OS is the software layer that prevents these cohorts from
                quietly decaying — by predicting churn before it happens, suggesting
                replacements before they're needed, and reaching donors in their own
                language on the channel they already use.
              </p>
            </div>

            <div className="rounded-2xl border border-accent/20 bg-gradient-to-br from-accent/5 to-primary/5 p-6">
              <p className="text-xs uppercase tracking-widest text-accent">
                Aligned with
              </p>
              <h3 className="mt-2 text-2xl font-semibold">
                Blood Warriors Foundation
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-white/70">
                Hyderabad-based foundation running the Blood Bridge programme
                across India. Their model is the inspiration; their workflows are
                what Bridge OS instruments.
              </p>
              <a
                href="https://bloodwarriors.in"
                target="_blank"
                rel="noopener noreferrer"
                className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline"
                data-testid="blood-warriors-link"
              >
                bloodwarriors.in
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* ---- Team ---- */}
      <section className="border-b border-white/5 px-6 py-20">
        <div className="mx-auto max-w-5xl">
          <div className="mb-10 flex items-center gap-3">
            <Users className="h-5 w-5 text-accent" />
            <p className="text-xs uppercase tracking-widest text-accent">Team</p>
          </div>
          <h2 className="text-3xl font-bold sm:text-4xl">AlgoWarriors</h2>

          <div className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-2">
            {TEAM.map((m) => (
              <article
                key={m.name}
                data-testid="team-card"
                className="rounded-2xl border border-white/5 bg-surface/40 p-7"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-primary to-accent text-lg font-bold text-background">
                  {m.name
                    .split(" ")
                    .map((p) => p[0])
                    .slice(0, 2)
                    .join("")}
                </div>
                <h3 className="mt-4 text-lg font-semibold">{m.name}</h3>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <a
                    href={m.linkedin}
                    target="_blank"
                    rel="noopener noreferrer"
                    data-testid="team-linkedin"
                    className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/80 transition hover:border-accent/40 hover:bg-accent/10 hover:text-accent"
                  >
                    <Linkedin className="h-3 w-3" />
                    LinkedIn
                  </a>
                  <a
                    href={m.github}
                    target="_blank"
                    rel="noopener noreferrer"
                    data-testid="team-github"
                    className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/80 transition hover:border-accent/40 hover:bg-accent/10 hover:text-accent"
                  >
                    <Github className="h-3 w-3" />
                    GitHub
                  </a>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ---- Values ---- */}
      <section className="border-b border-white/5 bg-surface/20 px-6 py-20">
        <div className="mx-auto max-w-5xl">
          <p className="text-xs uppercase tracking-widest text-accent">
            What we believe
          </p>
          <h2 className="mt-3 text-3xl font-bold sm:text-4xl">
            Three principles we held the whole build to
          </h2>

          <div className="mt-10 grid grid-cols-1 gap-5 md:grid-cols-3">
            {VALUES.map((v) => {
              const Icon = v.icon;
              return (
                <div
                  key={v.title}
                  className="rounded-2xl border border-white/5 bg-surface/40 p-6"
                >
                  <Icon className="h-5 w-5 text-accent" />
                  <h3 className="mt-4 text-lg font-semibold">{v.title}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-white/65">
                    {v.body}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ---- Hackathon credit ---- */}
      <section className="border-b border-white/5 px-6 py-20">
        <div className="mx-auto max-w-5xl">
          <div className="mb-10 flex items-center gap-3">
            <Award className="h-5 w-5 text-accent" />
            <p className="text-xs uppercase tracking-widest text-accent">
              The hackathon
            </p>
          </div>
          <h2 className="text-3xl font-bold sm:text-4xl">
            AI for Good Hackathon 2026
          </h2>
          <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-2">
            <CreditCard label="Organising sponsor" items={["Blend360"]} />
            <CreditCard
              label="Impact partners"
              items={["Blood Warriors Foundation", "HackCulture"]}
            />
          </div>
          <p className="mt-8 text-sm leading-relaxed text-white/55">
            Bridge OS was scoped, designed, built, and tested entirely during the
            hackathon window. Every commit lives in the local repository so the
            judges can audit the build trail.
          </p>
        </div>
      </section>

      {/* ---- CTA ---- */}
      <section className="px-6 py-24">
        <div className="mx-auto max-w-3xl text-center">
          <Sparkles className="mx-auto h-8 w-8 text-primary" />
          <h2 className="mt-6 text-3xl font-bold sm:text-4xl">
            Want to dig in?
          </h2>
          <p className="mt-4 text-base text-white/60">
            The whole product is open and clickable. No login. No demo data
            slideshow.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/bridges"
              className="inline-flex items-center gap-2 rounded-full bg-primary px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-primary/30 transition-colors hover:bg-primary-600"
            >
              Open dashboard
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/how-it-works"
              className="inline-flex items-center gap-2 rounded-full border border-white/15 px-6 py-3 text-sm font-medium text-white/80 transition-colors hover:border-white/30 hover:text-white"
            >
              How it works
            </Link>
          </div>
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}

function CreditCard({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="rounded-2xl border border-white/5 bg-surface/40 p-6">
      <p className="text-[11px] uppercase tracking-wider text-white/40">{label}</p>
      <ul className="mt-3 space-y-1">
        {items.map((it) => (
          <li key={it} className="text-base font-semibold text-white">
            {it}
          </li>
        ))}
      </ul>
    </div>
  );
}
