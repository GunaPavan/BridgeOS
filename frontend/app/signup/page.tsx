"use client";

import Link from "next/link";
import { Heart, Users } from "lucide-react";

export default function SignupChoicePage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-background to-surface/30 flex items-center justify-center px-4">
      <div className="w-full max-w-2xl">
        <Link href="/" className="block text-center mb-8">
          <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-4xl font-bold text-transparent">
            Bridge OS
          </span>
        </Link>
        <div className="rounded-2xl border border-white/10 bg-surface/40 p-8 backdrop-blur">
          <h1 className="text-2xl font-bold text-white">Create an account</h1>
          <p className="mt-1 text-sm text-white/60">
            Pick the role that matches you. Admin and coordinator accounts are
            created by the Blood Warriors team.
          </p>

          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Link
              href="/signup/donor"
              className="group rounded-xl border border-white/10 bg-black/20 p-6 hover:border-primary/50 hover:bg-primary/5"
            >
              <Heart className="h-8 w-8 text-primary" />
              <h2 className="mt-4 text-lg font-semibold text-white">
                I'm a donor
              </h2>
              <p className="mt-1 text-xs text-white/60">
                Sign up to see the patients you donate to, your donation
                history, cooldown windows, and update your preferences.
              </p>
              <span className="mt-4 inline-block text-xs text-primary group-hover:underline">
                Continue →
              </span>
            </Link>
            <Link
              href="/signup/patient"
              className="group rounded-xl border border-white/10 bg-black/20 p-6 hover:border-accent/50 hover:bg-accent/5"
            >
              <Users className="h-8 w-8 text-accent" />
              <h2 className="mt-4 text-lg font-semibold text-white">
                I'm a caregiver / patient
              </h2>
              <p className="mt-1 text-xs text-white/60">
                Sign up to see your bridge, transfusion schedule, who's been
                contacted, and manage your channel preferences.
              </p>
              <span className="mt-4 inline-block text-xs text-accent group-hover:underline">
                Continue →
              </span>
            </Link>
          </div>

          <div className="mt-6 border-t border-white/10 pt-4 text-center text-xs text-white/40">
            Already have an account?{" "}
            <Link href="/login" className="text-primary hover:underline">
              Sign in
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
