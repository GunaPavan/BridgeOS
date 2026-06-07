import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  CalendarClock,
  Cloud,
  Database,
  Droplet,
  KeyRound,
  Layers,
  Mail,
  MessageSquareText,
  Network,
  Play,
  Server,
  ShieldCheck,
  Siren,
  Sparkles,
  Workflow,
} from "lucide-react";

import { MarketingFooter } from "@/components/marketing/footer";
import { MarketingNav } from "@/components/marketing/nav";

export const metadata = {
  title: "How it works — Bridge OS",
  description:
    "The Bridge OS architecture: how XGBoost stability scoring, OR-Tools rotation, the cohort simulator, real WhatsApp, and the multilingual care agent compose into one product.",
};

export default function HowItWorksPage() {
  return (
    <div className="min-h-screen bg-background text-white">
      <MarketingNav />

      {/* ---- Hero ---- */}
      <section className="border-b border-white/5 px-6 py-20">
        <div className="mx-auto max-w-4xl">
          <p className="text-xs uppercase tracking-widest text-accent">
            How it works
          </p>
          <h1 className="mt-3 text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
            One product. Four AI systems. Zero slideware.
          </h1>
          <p className="mt-5 text-lg leading-relaxed text-white/65">
            Bridge OS keeps Blood Bridges healthy by combining cohort stability
            prediction, constraint-based scheduling, a live simulator, and a
            multilingual care agent — all over a shared data model and a Twilio
            WhatsApp surface that donors already use.
          </p>
        </div>
      </section>

      {/* ---- The problem ---- */}
      <section className="border-b border-white/5 bg-surface/20 px-6 py-20">
        <div className="mx-auto max-w-5xl">
          <div className="mb-10 flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 text-primary" />
            <p className="text-xs uppercase tracking-widest text-primary/80">
              The problem
            </p>
          </div>
          <h2 className="text-3xl font-bold sm:text-4xl">
            A 20-year coordination problem with 10 humans, 200 dates, one life
          </h2>

          <div className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-3">
            <ProblemTile
              n="100,000"
              label="thalassemia major patients in India"
              body="Every 18 days they need a transfusion. Miss it, and the patient is in the ER."
            />
            <ProblemTile
              n="8–10"
              label="committed donors per cohort"
              body="Blood Warriors' Blood Bridge model keeps the cohort small so trust builds — but the 90-day deferral rule means every donor can give at most 4 times a year."
            />
            <ProblemTile
              n="20+ years"
              label="of recurring care per patient"
              body="Donors burn out, move cities, miss replies. One quiet donor can cascade into a missed transfusion."
            />
          </div>

          <div className="mt-10 rounded-2xl border border-primary/20 bg-primary/5 p-6">
            <p className="text-sm text-white/80">
              <strong className="text-primary">The gap.</strong> Existing tools
              focus on one-off donor matching for emergencies. None scale the
              ongoing, multi-year coordination a Blood Bridge actually needs —
              so coordinators run it on WhatsApp, spreadsheets, and memory.
            </p>
          </div>
        </div>
      </section>

      {/* ---- Architecture diagram ---- */}
      <section className="border-b border-white/5 px-6 py-20">
        <div className="mx-auto max-w-5xl">
          <div className="mb-10 flex items-center gap-3">
            <Workflow className="h-5 w-5 text-accent" />
            <p className="text-xs uppercase tracking-widest text-accent">
              Architecture
            </p>
          </div>
          <h2 className="text-3xl font-bold sm:text-4xl">
            Production-deployed on AWS — ECS Fargate, RDS, Cognito, Bedrock, end-to-end
          </h2>
          <p className="mt-4 max-w-3xl text-sm leading-relaxed text-white/60">
            Bridge OS is not a local prototype. The backend runs on Amazon ECS
            Fargate behind an Application Load Balancer with an ACM cert at
            <code className="mx-1 rounded bg-white/5 px-1 text-accent">api.bridge-os.click</code>.
            Cognito guards every endpoint with role-based JWTs. EventBridge fires
            scheduled ticks, SQS absorbs outbound, SNS fans out events to Lambda,
            and CloudWatch alarms watch the lot.
          </p>

          <pre
            data-testid="architecture-diagram"
            className="mt-10 overflow-x-auto rounded-2xl border border-white/10 bg-black/40 p-6 font-mono text-[12px] leading-6 text-white/80"
          >{`┌─ FRONTEND  Next.js 14 · Tailwind · TanStack Query · Amplify ──┐
│   bridge-os.click                                               │
│   /bridges  /donors  /patients  /recommendations  /simulator    │
│   /analytics  /integrations  /whatsapp  /emails  /agent         │
│   /donor (self-service)   /patient (self-service)               │
│   /login   /signup → Cognito (donor / patient self-signup)      │
└──────────────────────────────┬─────────────────────────────────┘
                               │  HTTPS (Cognito ID-token JWT)
┌─ EDGE  ALB + ACM cert  api.bridge-os.click ────────────────────┐
│  Route 53 (apex + api + MX)   ACM TLS                           │
└──────────────────────────────┬─────────────────────────────────┘
                               │
┌─ BACKEND  ECS Fargate · FastAPI ─────────────────────────────────┐
│  Bridges / Donors / Patients ─ CRUD + filtered queries           │
│  Stability  ─ XGBoost churn 3-class + Survival GBM (C=0.751)     │
│  Schedule   ─ OR-Tools CP-SAT (90d deferral, distance min.)      │
│  Recommend  ─ Composite scorer (dist + resp + churn + kell)      │
│  Simulator  ─ Stateless what-if (no DB writes)                   │
│  Outreach   ─ WhatsApp / SMS / Email (per-donor preference)      │
│  Care Agent ─ AWS Bedrock Claude Sonnet 4.5 + Haiku + Titan v2   │
│  Escalation ─ Tiered call escalation w/ Twilio Voice <Gather>    │
│  RBAC       ─ Cognito groups: admin / coordinator / donor / pat  │
└─────┬───────────────┬───────────────┬───────────────┬──────────┘
      │               │               │               │
┌─────▼─ RDS ───┐ ┌───▼ SES ─────┐ ┌──▼ Bedrock ─┐ ┌──▼ Cognito ─┐
│ Postgres 16  │ │ Inbound (S3) │ │ Sonnet 4.5  │ │ User Pool   │
│ + pgvector   │ │ Outbound DKIM│ │ Haiku       │ │ + Post-     │
│              │ │ bridge-os.cl │ │ Titan v2    │ │   Confirm λ │
└──────────────┘ └──────────────┘ └─────────────┘ └─────────────┘
      │
┌─────▼ SQS ─────┐ ┌─ SNS ───────┐ ┌─ EventBridge ┐ ┌─ CloudWatch ┐
│ outbound      │ │ events fan- │ │ scheduled    │ │ dashboard   │
│ dispatch +    │ │ out → 2     │ │ ticks → λ →  │ │ + alarms    │
│ DLQ           │ │ Lambda subs │ │ /scheduler/* │ │ (SQS / SES) │
└───────────────┘ └─────────────┘ └──────────────┘ └─────────────┘
                                                    │
                                              ┌─────▼ Twilio ────┐
                                              │ WhatsApp · SMS  │
                                              │ Voice <Gather>  │
                                              └─────────────────┘`}</pre>
        </div>
      </section>

      {/* ---- AWS production deploy ---- */}
      <section className="border-b border-white/5 px-6 py-20">
        <div className="mx-auto max-w-5xl">
          <div className="mb-10 flex items-center gap-3">
            <Cloud className="h-5 w-5 text-sky-400" />
            <p className="text-xs uppercase tracking-widest text-sky-400">
              Live on AWS
            </p>
          </div>
          <h2 className="text-3xl font-bold sm:text-4xl">
            Sixteen AWS services in production — within a $40 budget
          </h2>
          <p className="mt-4 max-w-3xl text-sm leading-relaxed text-white/60">
            Every service below is wired and exercised by the live deploy.
            Mock mode still exists for local dev (the same code paths return
            deterministic data when AWS env vars are absent), but the
            <code className="mx-1 rounded bg-white/5 px-1 text-accent">bridge-os.click</code>
            instance uses the real thing end-to-end.
          </p>

          <div className="mt-10 grid grid-cols-1 gap-3 md:grid-cols-2">
            <AwsRow icon={Server} name="ECS Fargate · Express Mode" detail="x86_64 task running the FastAPI image behind an ALB. Replaces deprecated App Runner." />
            <AwsRow icon={Database} name="RDS Postgres 16 + pgvector" detail="t4g.micro Multi-AZ-ready. Holds donors, patients, bridges, agent memory embeddings." />
            <AwsRow icon={KeyRound} name="Cognito User Pool + Groups" detail="4 RBAC roles. PostConfirmation Lambda auto-assigns self-signups into donor/patient groups." />
            <AwsRow icon={Sparkles} name="Bedrock Claude Sonnet 4.5" detail="Multilingual care agent, reply intent classifier, voice <Gather> dialog brain." />
            <AwsRow icon={Mail} name="SES inbound + outbound" detail="MX on bridge-os.click receives caregiver replies; S3 poller pipes them into the same automation loop as WhatsApp." />
            <AwsRow icon={MessageSquareText} name="SQS dispatch queue + DLQ" detail="Outbound messages flow through SQS; poison pills land in a DLQ with a republish API." />
            <AwsRow icon={Network} name="SNS topics + Lambda subs" detail="Two topics (donor-events, bridge-events) fan out to Lambda subscribers for side effects." />
            <AwsRow icon={CalendarClock} name="EventBridge Scheduler" detail="Replaces APScheduler in-process ticks; fires scheduler/follow-up jobs into a Lambda that POSTs the backend." />
            <AwsRow icon={Cloud} name="ALB + ACM TLS" detail="api.bridge-os.click TLS-1.2 with ACM cert, listener-rule based path routing." />
            <AwsRow icon={Network} name="Route 53 hosted zone" detail="Apex bridge-os.click + api subdomain + MX records for SES inbound." />
            <AwsRow icon={Siren} name="CloudWatch dashboard + alarms" detail="Alerts on SQS depth, SES bounces, RDS CPU. Logs flow into /ecs/* groups." />
            <AwsRow icon={ShieldCheck} name="IAM least-privilege roles" detail="Task role only owns the resources it touches; secrets injected via env vars from the task def." />
          </div>
        </div>
      </section>

      {/* ---- Four differentiators deep dives ---- */}
      <section className="border-b border-white/5 bg-surface/20 px-6 py-20">
        <div className="mx-auto max-w-5xl">
          <p className="text-xs uppercase tracking-widest text-accent">
            The four differentiators
          </p>
          <h2 className="mt-3 text-3xl font-bold sm:text-4xl">
            Each one is a working AI system, not a button
          </h2>

          <div className="mt-12 space-y-12">
            <DifferentiatorDeepDive
              icon={BrainCircuit}
              number="1"
              title="Multi-class Churn Classifier + Survival Model"
              body={[
                "Two production models trained on real Blood Warriors donor data via a 6-algorithm bake-off each. The churn model (XGBoost — 0.979 macro AUC, 0.810 macro F1) predicts whether a donor is Active, Not-donated-1Y, or Limited-despite-calls — a 3-way intent signal, not a binary score.",
                "The survival model (Gradient Boosting Survival — C-index 0.751, 0.3 ms inference) returns a continuous 30/90/180/365-day retention curve so the cohort can be triaged by who's about to drift, not just who already has.",
                "Both models score the entire pool live on the analytics page — predicted engagement mix, intervention counts (needs-reminder / stop-calling), and 365-day survival quartiles — so coordinators see the network's risk shape, not just lagging indicators.",
              ]}
              link="/bridges"
              linkLabel="See a bridge's ML scoring →"
            />

            <DifferentiatorDeepDive
              icon={CalendarClock}
              number="2"
              title="OR-Tools CP-SAT Rotation Scheduler"
              body={[
                "Solves a 12-month rotation for each bridge. Hard constraints: donor must be eligible (>90 days since last donation), each donor capped at max(2, ceil(slots/donors)+2) slots, every transfusion in cadence must be filled.",
                "Objective minimises Σ(distance + (1 − response_rate)) per assignment — reliable nearby donors carry the load. Solves in ~50 ms even for 365-day horizons.",
                "Returns OPTIMAL / FEASIBLE / INFEASIBLE / EMPTY status. INFEASIBLE is itself a signal: 'the rotation broke, here are 3 candidates to fix it'.",
              ]}
              link="/bridges"
              linkLabel="See a schedule →"
            />

            <DifferentiatorDeepDive
              icon={Play}
              number="3"
              title="Live Cohort Simulator"
              body={[
                "Click any donor in the cohort to mark them ejected. The simulator runs stability + scheduler + recommender over BOTH the baseline cohort AND the post-action cohort in one pure-function call.",
                "Returns a ScenarioOutcome with baseline + scenario + a delta block (cohort size change, avg churn change, at-risk count change, scheduler status change). No database writes — fully replayable.",
                "Demo moment: eject Priya from Aarav's bridge → avg churn drops from 35% to 28%, 1 at-risk donor goes to 0, scheduler flips to INFEASIBLE, and the top 3 replacement candidates surface instantly.",
              ]}
              link="/simulator"
              linkLabel="Run a scenario →"
            />

            <DifferentiatorDeepDive
              icon={Sparkles}
              number="4"
              title="Multilingual LLM Care Agent + Real WhatsApp"
              body={[
                "Two channels, one brain. Outbound: coordinators send Twilio WhatsApp using auto-filled templates (slot_reminder, recruit_invite, thank_you, swap_request) or free-text. With TWILIO_* env vars the messages are real; without them, the same path stores mock rows.",
                "Inbound: donors reply on their phones; Twilio POSTs the form-encoded payload to /whatsapp/webhook, which stores the message and ACKs with TwiML.",
                "Care Agent: ask in any of 8 Indian languages (en, hi, te, ta, mr, bn, kn, gu). Per-entity context is assembled fresh — profile, recent WhatsApps, bridge memberships — and routed through AWS Bedrock (Claude Sonnet for chat, Haiku for intent, Titan v2 for memory embeddings) for grounded multilingual answers.",
              ]}
              link="/agent"
              linkLabel="Talk to the agent →"
            />
          </div>
        </div>
      </section>

      {/* ---- Coordinator's day flow ---- */}
      <section className="border-b border-white/5 px-6 py-20">
        <div className="mx-auto max-w-5xl">
          <div className="mb-10 flex items-center gap-3">
            <Activity className="h-5 w-5 text-accent" />
            <p className="text-xs uppercase tracking-widest text-accent">
              A coordinator's day on Bridge OS
            </p>
          </div>
          <h2 className="text-3xl font-bold sm:text-4xl">
            From morning triage to evening confirmation, in five clicks
          </h2>

          <ol className="mt-10 space-y-5">
            <StepRow
              n="08:30"
              icon={Activity}
              title="Open Recommendations"
              body="The inbox is pre-sorted by urgency. Aarav's bridge is flagged critical — Priya (response rate 32%, last donation 120 days ago) is the destabiliser."
            />
            <StepRow
              n="08:32"
              icon={Network}
              title="Pick a replacement"
              body="Three ranked candidates show with composite scores. Top: Aishwarya Murthy — 2.3 km away, 95% response rate, 12% predicted churn, Kell-negative match."
            />
            <StepRow
              n="08:34"
              icon={Play}
              title="Verify with the simulator"
              body="Eject Priya, add Aishwarya. Avg churn drops from 35% to 14%. Scheduler returns OPTIMAL. Confirm."
            />
            <StepRow
              n="08:36"
              icon={MessageSquareText}
              title="Send a Hindi welcome"
              body="Open WhatsApp, pick Aishwarya, choose recruit_invite template. The template fills 'Aarav' and 'B+' automatically. Send."
            />
            <StepRow
              n="08:38"
              icon={Sparkles}
              title="Ask the agent why"
              body="On /agent, pick Aarav's bridge as context, ask 'Why was this swap necessary?' in Hindi. The agent cites Priya's signals and the scheduler's INFEASIBLE status before the swap."
            />
          </ol>
        </div>
      </section>

      {/* ---- Tech stack strip ---- */}
      <section className="border-b border-white/5 bg-surface/20 px-6 py-20">
        <div className="mx-auto max-w-5xl">
          <div className="mb-10 flex items-center gap-3">
            <Layers className="h-5 w-5 text-accent" />
            <p className="text-xs uppercase tracking-widest text-accent">
              Stack
            </p>
          </div>
          <h2 className="text-3xl font-bold sm:text-4xl">
            Open-source ML + Indian public infrastructure
          </h2>

          <div className="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <StackTile icon={BrainCircuit} group="ML" label="XGBoost + SHAP" />
            <StackTile icon={CalendarClock} group="Optim" label="Google OR-Tools (CP-SAT)" />
            <StackTile icon={Sparkles} group="LLM" label="Bedrock Claude 4.5 + Titan v2" />
            <StackTile icon={MessageSquareText} group="Comms" label="Twilio WhatsApp + Voice" />
            <StackTile icon={Mail} group="Comms" label="Amazon SES (in/out)" />
            <StackTile icon={Droplet} group="Data" label="eRaktKosh inventory" />
            <StackTile icon={Database} group="Data" label="ICMR Rare Donor Registry" />
            <StackTile icon={Server} group="Compute" label="ECS Fargate · Express Mode" />
            <StackTile icon={Database} group="DB" label="RDS Postgres 16 + pgvector" />
            <StackTile icon={KeyRound} group="Auth" label="Cognito User Pool + groups" />
            <StackTile icon={CalendarClock} group="Sched" label="EventBridge → Lambda" />
            <StackTile icon={Network} group="Bus" label="SQS + DLQ + SNS topics" />
            <StackTile icon={Siren} group="Obs" label="CloudWatch dashboard" />
            <StackTile icon={Cloud} group="Edge" label="ALB + ACM + Route 53" />
            <StackTile icon={Network} group="Backend" label="FastAPI + SQLAlchemy 2" />
            <StackTile icon={Workflow} group="Frontend" label="Next.js 14 + Amplify" />
          </div>
        </div>
      </section>

      {/* ---- CTA ---- */}
      <section className="px-6 py-24">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="text-3xl font-bold sm:text-4xl">
            Ready to try it?
          </h2>
          <p className="mt-4 text-base text-white/60">
            Every model, scheduler, and integration runs against real Blood
            Warriors-style donor data on the live AWS deploy. Sign in as a
            coordinator to drive it, or sign up as donor / patient for the
            self-service portal.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/login"
              className="inline-flex items-center gap-2 rounded-full bg-primary px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-primary/30 transition-colors hover:bg-primary-600"
            >
              Sign in
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/signup"
              className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-6 py-3 text-sm font-medium text-primary transition-colors hover:bg-primary/20"
            >
              Sign up as donor / patient
            </Link>
            <Link
              href="/about"
              className="inline-flex items-center gap-2 rounded-full border border-white/15 px-6 py-3 text-sm font-medium text-white/80 transition-colors hover:border-white/30 hover:text-white"
            >
              About the team
            </Link>
          </div>
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}

// ---------- subcomponents ----------

function ProblemTile({ n, label, body }: { n: string; label: string; body: string }) {
  return (
    <div className="rounded-2xl border border-white/5 bg-surface/40 p-6">
      <p className="bg-gradient-to-r from-primary to-accent bg-clip-text text-4xl font-bold text-transparent">
        {n}
      </p>
      <p className="mt-2 text-sm font-medium text-white/80">{label}</p>
      <p className="mt-3 text-xs leading-relaxed text-white/55">{body}</p>
    </div>
  );
}

function DifferentiatorDeepDive({
  icon: Icon,
  number,
  title,
  body,
  link,
  linkLabel,
}: {
  icon: React.ComponentType<{ className?: string }>;
  number: string;
  title: string;
  body: string[];
  link: string;
  linkLabel: string;
}) {
  return (
    <article
      data-testid="differentiator-deepdive"
      className="rounded-2xl border border-white/5 bg-surface/40 p-7"
    >
      <div className="flex items-start gap-4">
        <div className="rounded-lg bg-primary/10 p-3 ring-1 ring-primary/20">
          <Icon className="h-5 w-5 text-primary" />
        </div>
        <div className="flex-1">
          <p className="text-[11px] uppercase tracking-widest text-accent">
            Differentiator #{number}
          </p>
          <h3 className="mt-1 text-xl font-semibold">{title}</h3>
        </div>
      </div>
      <div className="mt-5 space-y-3">
        {body.map((p, i) => (
          <p key={i} className="text-sm leading-relaxed text-white/65">
            {p}
          </p>
        ))}
      </div>
      <Link
        href={link}
        className="mt-5 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
      >
        {linkLabel}
      </Link>
    </article>
  );
}

function StepRow({
  n,
  icon: Icon,
  title,
  body,
}: {
  n: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
}) {
  return (
    <li className="flex items-start gap-4 rounded-xl border border-white/5 bg-surface/30 p-5">
      <span className="rounded-md bg-black/40 px-2 py-1 font-mono text-xs text-accent">
        {n}
      </span>
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-white/60" />
          <h4 className="text-sm font-semibold">{title}</h4>
        </div>
        <p className="mt-1 text-sm text-white/60">{body}</p>
      </div>
    </li>
  );
}

function StackTile({
  icon: Icon,
  group,
  label,
}: {
  icon: React.ComponentType<{ className?: string }>;
  group: string;
  label: string;
}) {
  return (
    <div className="rounded-xl border border-white/5 bg-surface/40 px-4 py-3">
      <p className="text-[10px] uppercase tracking-wider text-white/40">{group}</p>
      <div className="mt-1 flex items-center gap-2">
        <Icon className="h-3.5 w-3.5 text-accent" />
        <p className="text-xs font-medium text-white/85">{label}</p>
      </div>
    </div>
  );
}

function AwsRow({
  icon: Icon,
  name,
  detail,
}: {
  icon: React.ComponentType<{ className?: string }>;
  name: string;
  detail: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-white/5 bg-surface/40 p-4">
      <div className="rounded-lg bg-sky-500/10 p-2 ring-1 ring-sky-500/20">
        <Icon className="h-4 w-4 text-sky-400" />
      </div>
      <div className="flex-1">
        <p className="text-sm font-semibold text-white">{name}</p>
        <p className="mt-1 text-xs leading-relaxed text-white/60">{detail}</p>
      </div>
    </div>
  );
}
